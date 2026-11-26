import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from backend.logica.pagos_transferencia import preparar_pago_transferencia
from backend.logica.pagos_contraentrega import preparar_pago_contraentrega, validar_producto_para_contraentrega
from backend.logica.moneda import validar_importe_entero

CUENTAS = "bank_accounts"
ORDENES = "orders"
CARRITO = "cart"
PRODUCTOS = "products"
IDEMPOTENCIA = "checkout_idempotency"


def inicializar_indices_checkout(db: Any) -> None:
    # Se crea antes de iniciar transacciones; evita crear una colección nueva
    # dentro de una transacción distribuida entre shards.
    db[IDEMPOTENCIA].create_index(
        [("userId", 1), ("createdAt", -1)],
        name="idx_checkout_idempotency_user_created",
    )


def _money(value: Any, *, allow_zero: bool = False) -> int:
    try:
        return validar_importe_entero(value, permitir_cero=allow_zero)
    except HTTPException as error:
        raise HTTPException(status_code=409, detail="INVALID_AMOUNT") from error


def _coupon_discount(db: Any, code: str, subtotal: int, session: Any) -> int:
    if not code:
        return 0
    from backend.logica.cupones import calcular_descuento_cupon
    _, discount = calcular_descuento_cupon(db, code, subtotal, session=session)
    return discount


def _idempotency_id(user_id: str, key: str) -> str:
    raw = f"{user_id}:{key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _checkout_key(data: dict, supplied_key: str | None) -> str:
    key = str(supplied_key or data.get("idempotencyKey") or "").strip()
    if key:
        if len(key) > 200:
            raise HTTPException(status_code=400, detail="INVALID_IDEMPOTENCY_KEY")
        return key
    # Compatibilidad con clientes existentes: los IDs del carrito permanecen
    # en la solicitud aunque el primer intento haya vaciado el carrito.
    selected = data.get("selectedCartItemIds")
    if not isinstance(selected, list) or not selected:
        raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_REQUIRED")
    fingerprint = {
        "items": sorted(str(value).strip() for value in selected),
        "method": str(data.get("paymentMethod") or "").strip().lower(),
        "bankAccountId": str(data.get("bankAccountId") or "").strip(),
        "couponCode": str(data.get("couponCode") or "").strip().upper(),
        "codTerms": str(data.get("cashOnDeliveryTermsVersion") or ""),
    }
    return hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode("utf-8")).hexdigest()


def _existing_order(db: Any, idem_id: str, session: Any) -> dict | None:
    record = db[IDEMPOTENCIA].find_one({"_id": idem_id}, session=session)
    if not record:
        return None
    order = db[ORDENES].find_one({"_id": record["orderId"]}, session=session)
    if order is None:
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_RECORD_INCOMPLETE")
    result = dict(order)
    result.pop("_id", None)
    return {"success": True, "order": {"id": record["orderId"], **result}, "idempotentReplay": True}


def crear_orden_pago(db: Any, user: dict, data: dict, idempotency_key: str | None = None) -> dict:
    method = str(data.get("paymentMethod") or "").strip().lower()
    if method not in ("bank_transfer", "cash_on_delivery"):
        raise HTTPException(status_code=400, detail="INVALID_PAYMENT_METHOD")

    user_id = str(user["_id"])
    key = _checkout_key(data, idempotency_key)
    idem_id = _idempotency_id(user_id, key)
    selected_ids = data.get("selectedCartItemIds")
    if not isinstance(selected_ids, list) or not selected_ids:
        raise HTTPException(status_code=400, detail="CART_ITEMS_SELECTION_REQUIRED")
    selected_ids = [str(value).strip() for value in selected_ids]
    if any(not value for value in selected_ids) or len(set(selected_ids)) != len(selected_ids):
        raise HTTPException(status_code=400, detail="INVALID_CART_ITEMS_SELECTION")

    def ejecutar(session: Any) -> dict:
        replay = _existing_order(db, idem_id, session)
        if replay is not None:
            return replay

        now = datetime.now(timezone.utc)
        preparador = preparar_pago_transferencia if method == "bank_transfer" else preparar_pago_contraentrega
        payment_details = preparador(db, data, now, session=session)

        selected_cart = list(db[CARRITO].find(
            {"userId": user_id, "_id": {"$in": selected_ids}}, session=session
        ))
        if not selected_cart:
            raise HTTPException(status_code=400, detail="CART_EMPTY")
        if len(selected_cart) != len(selected_ids):
            raise HTTPException(status_code=409, detail="CART_ITEMS_CHANGED")

        items, subtotal, shipping = [], 0, 0
        quantities_by_product: dict[str, int] = {}
        for entry in selected_cart:
            product_id = str(entry.get("productId") or "")
            qty = entry.get("quantity")
            if not product_id or isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
                raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
            product = db[PRODUCTOS].find_one({"_id": product_id}, session=session)
            if product is None:
                raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
            if method == "cash_on_delivery":
                validar_producto_para_contraentrega(product)
            price = _money(product.get("price"))
            shipping_id = str(entry.get("selectedShippingId") or "")
            methods = product.get("shippingMethods") or []
            ship_method = next((m for m in methods if str(m.get("id") or "") == shipping_id), None) if shipping_id else None
            if methods and ship_method is None:
                raise HTTPException(status_code=409, detail="SHIPPING_METHOD_REQUIRED")
            ship_price = _money(ship_method.get("price", 0), allow_zero=True) if ship_method else 0
            subtotal += price * qty
            shipping += ship_price
            quantities_by_product[product_id] = quantities_by_product.get(product_id, 0) + qty
            items.append({
                "productId": product_id, "name": str(product.get("name") or "Producto")[:200],
                "priceDOP": price, "quantity": qty,
                "shippingMethodId": ship_method.get("id", "") if ship_method else "",
                "shippingMethodName": ship_method.get("name", "") if ship_method else "",
                "shippingPriceDOP": ship_price,
                "selectedSize": entry.get("selectedSize"), "selectedColor": entry.get("selectedColor"),
            })

        coupon_code = str(data.get("couponCode") or "").strip().upper()
        discount = _coupon_discount(db, coupon_code, subtotal, session)
        total = subtotal - discount + shipping
        if total <= 0:
            raise HTTPException(status_code=409, detail="INVALID_ORDER_TOTAL")

        # Cada descuento de stock y la creación del pedido ocurren dentro
        # de la misma transacción MongoDB.
        for product_id, quantity in quantities_by_product.items():
            result = db[PRODUCTOS].update_one(
                {"_id": product_id, "stock": {"$gte": quantity}},
                {"$inc": {"stock": -quantity}},
                session=session,
            )
            if result.modified_count != 1:
                raise HTTPException(status_code=409, detail="INSUFFICIENT_STOCK")

        order_id = idem_id
        order = {
            "_id": order_id, "userId": user_id,
            "customerName": str(data.get("customerName") or user.get("name") or "").strip(),
            "email": str(data.get("email") or user.get("email") or "").strip(),
            "phone": str(data.get("phone") or "").strip(),
            "address": str(data.get("address") or "").strip(),
            "city": str(data.get("city") or "").strip(),
            "items": items, "itemCount": sum(i["quantity"] for i in items),
            "itemsSummary": ", ".join(f'{i["name"]} x{i["quantity"]}' for i in items),
            "subtotalDOP": subtotal, "shippingTotalDOP": shipping,
            "couponCode": coupon_code, "couponDiscountDOP": discount,
            "total": total, "totalDOP": total, "currency": "DOP",
            "paymentMethod": method, **payment_details,
            "paymentProofUrl": "", "createdAt": now, "updatedAt": now,
            "inventoryReserved": True, "reservationStatus": "active",
            "idempotencyKeyHash": idem_id,
        }
        if not order["customerName"] or not order["address"] or not order["city"] or not order["phone"]:
            raise HTTPException(status_code=400, detail="DELIVERY_FIELDS_REQUIRED")

        db[ORDENES].insert_one(order, session=session)
        db[IDEMPOTENCIA].insert_one({
            "_id": idem_id, "userId": user_id, "orderId": order_id,
            "createdAt": now,
        }, session=session)
        db[CARRITO].delete_many(
            {"userId": user_id, "_id": {"$in": selected_ids}}, session=session
        )
        response_order = dict(order)
        response_order.pop("_id", None)
        return {"success": True, "order": {"id": order_id, **response_order}}

    try:
        with db.client.start_session() as session:
            return session.with_transaction(ejecutar)
    except DuplicateKeyError:
        # Dos solicitudes concurrentes con la misma clave: recuperar la orden
        # que confirmó la primera transacción, sin reservar stock otra vez.
        with db.client.start_session() as session:
            replay = _existing_order(db, idem_id, session)
        if replay is not None:
            return replay
        raise HTTPException(status_code=409, detail="CHECKOUT_CONFLICT")
