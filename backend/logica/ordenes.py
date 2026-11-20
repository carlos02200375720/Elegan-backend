import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection

NOMBRE_COLECCION_ORDENES = "orders"
NOMBRE_COLECCION_CARRITO = "cart"


def coleccion_ordenes(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_ORDENES]


def inicializar_indices_ordenes(db: Any) -> None:
    coleccion = coleccion_ordenes(db)
    coleccion.create_index(
        [("userId", 1), ("createdAt", DESCENDING)],
        name="idx_orders_user_created_at",
    )
    coleccion.create_index([("status", 1)], name="idx_orders_status")
    coleccion.create_index(
        [("createdAt", DESCENDING)], name="idx_orders_created_at"
    )


def formatear_orden(documento: dict) -> dict:
    orden = dict(documento)
    orden["id"] = str(orden.pop("_id"))
    return orden


def listar_ordenes(db: Any, user: dict, solo_usuario: bool) -> dict:
    filtro = {"userId": str(user["_id"])} if solo_usuario else {}
    filas = coleccion_ordenes(db).find(filtro).sort("createdAt", DESCENDING)
    return {"items": [formatear_orden(fila) for fila in filas]}


def actualizar_estado_orden(db: Any, order_id: str, status: str) -> dict:
    coleccion = coleccion_ordenes(db)
    existente = coleccion.find_one({"_id": order_id})
    if existente is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    if existente.get("paymentMethod") == "bank_transfer" and existente.get("paymentStatus") != "verified":
        raise HTTPException(status_code=409, detail="TRANSFERMENT_NOT_VERIFIED")
    if existente.get("paymentStatus") in ("pending", "awaiting_proof", "proof_submitted", "proof_rejected"):
        raise HTTPException(status_code=409, detail="ORDER_PAYMENT_PENDING")

    resultado = coleccion.update_one(
        {"_id": order_id},
        {
            "$set": {
                "status": status,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")

    orden = coleccion.find_one({"_id": order_id})
    return formatear_orden(orden)
