from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pymongo import ASCENDING

CUENTAS = "bank_accounts"
ORDENES = "orders"
CARRITO = "cart"
PRODUCTOS = "products"
CENTAVO = Decimal("0.01")
COD_TERMS_VERSION = "2026-11-19"
CONFIG_COD = "payment_settings"
CONFIG_COD_ID = "cash_on_delivery"
COD_DEFAULT_MESSAGE = "Paga tu pedido cuando lo recibas. Verifica los productos y confirma la recepción al momento de la entrega."


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


def _money(value: Any, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="INVALID_AMOUNT")
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise HTTPException(status_code=409, detail="INVALID_AMOUNT")
    return amount.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _format_account(doc: dict) -> dict:
    row = dict(doc)
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


def _coupon_discount(db: Any, code: str, subtotal: Decimal) -> Decimal:
    if not code:
        return Decimal("0.00")
    from backend.logica.cupones import calcular_descuento_cupon
    _, discount = calcular_descuento_cupon(db, code, subtotal)
    return discount


def obtener_configuracion_contraentrega(db: Any) -> dict:
    config = db[CONFIG_COD].find_one({"_id": CONFIG_COD_ID}) or {}
    return {
        "enabled": bool(config.get("enabled", True)),
        "message": str(config.get("message") or COD_DEFAULT_MESSAGE),
        "termsVersion": COD_TERMS_VERSION,
    }


def actualizar_configuracion_contraentrega(db: Any, data: dict) -> dict:
    enabled = data.get("enabled")
    message = data.get("message")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="COD_ENABLED_BOOLEAN_REQUIRED")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="COD_MESSAGE_REQUIRED")
    now = datetime.now(timezone.utc)
    db[CONFIG_COD].update_one(
        {"_id": CONFIG_COD_ID},
        {"$set": {"enabled": enabled, "message": message.strip()[:3000], "updatedAt": now},
         "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    return obtener_configuracion_contraentrega(db)


def crear_orden_pago(db: Any, user: dict, data: dict) -> dict:
    _liberar_transferencias_vencidas(db)
    method = str(data.get("paymentMethod") or "").strip().lower()
    if method not in ("bank_transfer", "cash_on_delivery"):
        raise HTTPException(status_code=400, detail="INVALID_PAYMENT_METHOD")
    if method == "cash_on_delivery" and not obtener_configuracion_contraentrega(db)["enabled"]:
        raise HTTPException(status_code=409, detail="COD_DISABLED")
    if method == "cash_on_delivery" and (
        data.get("cashOnDeliveryAccepted") is not True
        or data.get("cashOnDeliveryTermsVersion") != COD_TERMS_VERSION
    ):
        raise HTTPException(status_code=400, detail="COD_TERMS_NOT_ACCEPTED")

    account = None
    if method == "bank_transfer":
        account_id = str(data.get("bankAccountId") or "").strip()
        account = db[CUENTAS].find_one({"_id": account_id, "isActive": True})
        if account is None:
            raise HTTPException(status_code=409, detail="BANK_ACCOUNT_UNAVAILABLE")

    user_id = str(user["_id"])
    cart = list(db[CARRITO].find({"userId": user_id}))
    if not cart:
        raise HTTPException(status_code=400, detail="CART_EMPTY")
    selected_ids = data.get("selectedCartItemIds")
    if not isinstance(selected_ids, list) or not selected_ids:
        raise HTTPException(status_code=400, detail="CART_ITEMS_SELECTION_REQUIRED")
    selected_ids = [str(value).strip() for value in selected_ids]
    if any(not value for value in selected_ids) or len(set(selected_ids)) != len(selected_ids):
        raise HTTPException(status_code=400, detail="INVALID_CART_ITEMS_SELECTION")
    selected_cart = [entry for entry in cart if str(entry.get("_id")) in set(selected_ids)]
    if len(selected_cart) != len(selected_ids):
        raise HTTPException(status_code=409, detail="CART_ITEMS_CHANGED")
    cart = selected_cart

    items, subtotal, shipping = [], Decimal("0.00"), Decimal("0.00")
    for entry in cart:
        product_id, qty = str(entry.get("productId") or ""), entry.get("quantity")
        if not product_id or isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
        product = db[PRODUCTOS].find_one({"_id": product_id})
        if product is None:
            raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
        if method == "cash_on_delivery" and product.get("allowCashOnDelivery", True) is not True:
            raise HTTPException(status_code=409, detail="COD_PRODUCT_NOT_ALLOWED")
        price = _money(product.get("price"))
        stock = product.get("stock")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < qty:
            raise HTTPException(status_code=409, detail="INSUFFICIENT_STOCK")
        shipping_id = str(entry.get("selectedShippingId") or "")
        methods = product.get("shippingMethods") or []
        ship_method = next((m for m in methods if str(m.get("id") or "") == shipping_id), None) if shipping_id else None
        if methods and ship_method is None:
            raise HTTPException(status_code=409, detail="SHIPPING_METHOD_REQUIRED")
        ship_price = _money(ship_method.get("price", 0), allow_zero=True) if ship_method else Decimal("0.00")
        subtotal += price * qty
        shipping += ship_price
        items.append({"productId": product_id, "name": str(product.get("name") or "Producto")[:200],
                      "priceDOP": format(price, ".2f"), "quantity": qty,
                      "shippingMethodId": ship_method.get("id", "") if ship_method else "",
                      "shippingMethodName": ship_method.get("name", "") if ship_method else "",
                      "shippingPriceDOP": format(ship_price, ".2f"),
                      "selectedSize": entry.get("selectedSize"), "selectedColor": entry.get("selectedColor")})
    subtotal, shipping = subtotal.quantize(CENTAVO), shipping.quantize(CENTAVO)
    coupon_code = str(data.get("couponCode") or "").strip().upper()
    discount = _coupon_discount(db, coupon_code, subtotal)
    total = (subtotal - discount + shipping).quantize(CENTAVO)
    if total <= 0:
        raise HTTPException(status_code=409, detail="INVALID_ORDER_TOTAL")

    # Stock is reserved atomically per product; rollback prior reservations on failure.
    reserved = []
    order_id = None
    try:
        for item in items:
            result = db[PRODUCTOS].update_one(
                {"_id": item["productId"], "stock": {"$gte": item["quantity"]}},
                {"$inc": {"stock": -item["quantity"]}},
            )
            if not result.modified_count:
                raise HTTPException(status_code=409, detail="INSUFFICIENT_STOCK")
            reserved.append(item)
        now, order_id = datetime.now(timezone.utc), str(uuid4())
        order = {
            "_id": order_id, "userId": user_id, "customerName": str(data.get("customerName") or user.get("name") or "").strip(),
            "email": str(data.get("email") or user.get("email") or "").strip(),
            "phone": str(data.get("phone") or "").strip(), "address": str(data.get("address") or "").strip(),
            "city": str(data.get("city") or "").strip(), "items": items,
            "itemCount": sum(i["quantity"] for i in items),
            "itemsSummary": ", ".join(f'{i["name"]} x{i["quantity"]}' for i in items),
            "subtotalDOP": format(subtotal, ".2f"), "shippingTotalDOP": format(shipping, ".2f"),
            "couponCode": coupon_code, "couponDiscountDOP": format(discount, ".2f"),
            "total": format(total, ".2f"), "totalDOP": format(total, ".2f"), "currency": "DOP",
            "paymentMethod": method, "paymentStatus": "awaiting_proof" if method == "bank_transfer" else "cash_on_delivery",
            "status": "pendiente_pago" if method == "bank_transfer" else "pendiente_confirmacion",
            "cashOnDeliveryAccepted": method == "cash_on_delivery",
            "cashOnDeliveryTermsVersion": COD_TERMS_VERSION if method == "cash_on_delivery" else None,
            "cashOnDeliveryAcceptedAt": now if method == "cash_on_delivery" else None,
            "expiresAt": now + timedelta(hours=24) if method == "bank_transfer" else None,
            "bankAccount": {"id": account["id"], "bankName": account["bankName"],
                            "accountNumber": account["accountNumber"], "accountType": account["accountType"],
                            "holderName": account["holderName"], "holderDocument": account.get("holderDocument", "")} if account else None,
            "paymentProofUrl": "", "createdAt": now, "updatedAt": now,
            "inventoryReserved": True,
        }
        if not order["customerName"] or not order["address"] or not order["city"] or not order["phone"]:
            raise HTTPException(status_code=400, detail="DELIVERY_FIELDS_REQUIRED")
        db[ORDENES].insert_one(order)
        # Solo se retiran del carrito las filas exactas incluidas en esta orden.
        db[CARRITO].delete_many({"userId": user_id, "_id": {"$in": selected_ids}})
        order.pop("_id", None)
        return {"success": True, "order": {"id": order_id, **order}}
    except Exception:
        if order_id:
            db[ORDENES].delete_one({"_id": order_id})
        for item in reserved:
            db[PRODUCTOS].update_one({"_id": item["productId"]}, {"$inc": {"stock": item["quantity"]}})
        raise


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
