from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pymongo import ASCENDING

CUENTAS = "bank_accounts"
ORDENES = "orders"
PRODUCTOS = "products"


def preparar_pago_transferencia(db: Any, data: dict, now: datetime) -> dict:
    account_id = str(data.get("bankAccountId") or "").strip()
    account = db[CUENTAS].find_one({"_id": account_id, "isActive": True})
    if account is None:
        raise HTTPException(status_code=409, detail="BANK_ACCOUNT_UNAVAILABLE")
    account_public_id = str(account.get("id") or account.get("_id") or "").strip()
    if not account_public_id:
        raise HTTPException(status_code=409, detail="BANK_ACCOUNT_UNAVAILABLE")
    return {
        "paymentStatus": "awaiting_proof",
        "status": "pendiente_pago",
        "cashOnDeliveryAccepted": False,
        "cashOnDeliveryTermsVersion": None,
        "cashOnDeliveryAcceptedAt": None,
        "expiresAt": now + timedelta(hours=24),
        "bankAccount": {
            "id": account_public_id, "bankName": account["bankName"],
            "accountNumber": account["accountNumber"], "accountType": account["accountType"],
            "holderName": account["holderName"], "holderDocument": account.get("holderDocument", ""),
        },
    }


def inicializar_indices_cuentas_bancarias(db: Any) -> None:
    db[CUENTAS].create_index([("id", ASCENDING)], unique=True, name="idx_bank_accounts_id")
    db[CUENTAS].create_index([("isActive", ASCENDING)], name="idx_bank_accounts_active")


def _liberar_transferencias_vencidas(db: Any) -> None:
    now = datetime.now(timezone.utc)
    expired = db[ORDENES].find({
        "paymentMethod": "bank_transfer",
        "paymentStatus": {"$in": ["awaiting_proof", "proof_rejected"]},
        "inventoryReserved": True,
        "expiresAt": {"$lte": now},
    })
    for order in expired:
        changed = db[ORDENES].update_one(
            {"_id": order["_id"], "inventoryReserved": True,
             "paymentStatus": {"$in": ["awaiting_proof", "proof_rejected"]}},
            {"$set": {"paymentStatus": "expired", "status": "cancelado",
                      "inventoryReserved": False, "updatedAt": now}},
        )
        if changed.modified_count:
            for item in order.get("items", []):
                db[PRODUCTOS].update_one(
                    {"_id": item["productId"]},
                    {"$inc": {"stock": int(item["quantity"])}},
                )


def liberar_transferencias_vencidas(db: Any) -> None:
    _liberar_transferencias_vencidas(db)


def _format_account(doc: dict) -> dict:
    row = dict(doc)
    # Compatibilidad con cuentas antiguas que solo tienen _id en MongoDB.
    row["id"] = str(row.get("id") or row.get("_id") or "").strip()
    row.pop("_id", None)
    return row


def listar_cuentas_bancarias(db: Any, solo_activas: bool = False) -> dict:
    filtro = {"isActive": True} if solo_activas else {}
    return {"items": [_format_account(row) for row in db[CUENTAS].find(filtro).sort("bankName", 1)]}


def crear_cuenta_bancaria(db: Any, data: dict) -> dict:
    bank = str(data.get("bankName") or "").strip()
    number = str(data.get("accountNumber") or "").strip()
    holder = str(data.get("holderName") or "").strip()
    account_type = str(data.get("accountType") or "").strip()
    if not bank or not number or not holder or not account_type:
        raise HTTPException(status_code=400, detail="BANK_ACCOUNT_FIELDS_REQUIRED")
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    row = {"_id": account_id, "id": account_id, "bankName": bank[:100],
           "accountNumber": number[:80], "accountType": account_type[:50],
           "holderName": holder[:150], "holderDocument": str(data.get("holderDocument") or "").strip()[:40],
           "isActive": bool(data.get("isActive", True)), "createdAt": now, "updatedAt": now}
    db[CUENTAS].insert_one(row)
    return _format_account(row)


def actualizar_cuenta_bancaria(db: Any, account_id: str, data: dict) -> dict:
    allowed = {"bankName", "accountNumber", "accountType", "holderName", "holderDocument", "isActive"}
    update = {k: v for k, v in data.items() if k in allowed and v is not None}
    for key in ("bankName", "accountNumber", "accountType", "holderName", "holderDocument"):
        if key in update:
            update[key] = str(update[key]).strip()
    if any(not update.get(k) for k in ("bankName", "accountNumber", "accountType", "holderName") if k in update):
        raise HTTPException(status_code=400, detail="BANK_ACCOUNT_FIELDS_REQUIRED")
    update["updatedAt"] = datetime.now(timezone.utc)
    result = db[CUENTAS].update_one({"_id": account_id}, {"$set": update})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="BANK_ACCOUNT_NOT_FOUND")
    return _format_account(db[CUENTAS].find_one({"_id": account_id}))


def eliminar_cuenta_bancaria(db: Any, account_id: str) -> dict:
    # Los pedidos guardan una copia de los datos bancarios elegidos.
    result = db[CUENTAS].delete_one({"_id": account_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="BANK_ACCOUNT_NOT_FOUND")
    return {"success": True}


def adjuntar_comprobante(db: Any, user: dict, order_id: str, proof_object_name: str) -> dict:
    _liberar_transferencias_vencidas(db)
    order = db[ORDENES].find_one({"_id": order_id, "userId": str(user["_id"])})
    if order is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    if order.get("paymentMethod") != "bank_transfer" or order.get("paymentStatus") not in ("awaiting_proof", "proof_rejected"):
        raise HTTPException(status_code=409, detail="PROOF_NOT_ALLOWED")
    if not proof_object_name.startswith("comprobantes/"):
        raise HTTPException(status_code=400, detail="INVALID_PROOF_OBJECT")
    now = datetime.now(timezone.utc)
    db[ORDENES].update_one({"_id": order_id}, {"$set": {
        "paymentProofObjectName": proof_object_name, "paymentStatus": "proof_submitted",
        "status": "pendiente_validacion", "proofSubmittedAt": now, "updatedAt": now,
    }})
    return {"success": True, "id": order_id, "paymentStatus": "proof_submitted"}


def revisar_pago_transferencia(db: Any, order_id: str, approved: bool, note: str = "") -> dict:
    order = db[ORDENES].find_one({"_id": order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    if order.get("status") == "cancelado":
        raise HTTPException(status_code=409, detail="ORDER_CANCELLED")
    if order.get("paymentMethod") != "bank_transfer" or order.get("paymentStatus") != "proof_submitted":
        raise HTTPException(status_code=409, detail="PAYMENT_NOT_REVIEWABLE")
    now = datetime.now(timezone.utc)
    update = {"paymentStatus": "verified" if approved else "proof_rejected",
              "status": "confirmado" if approved else "comprobante_rechazado",
              "paymentReviewedAt": now, "paymentReviewNote": str(note or "")[:500], "updatedAt": now}
    db[ORDENES].update_one({"_id": order_id}, {"$set": update})
    return {"success": True, "paymentStatus": update["paymentStatus"], "status": update["status"]}
