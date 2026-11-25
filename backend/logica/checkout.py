from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend.logica.pagos_transferencia import liberar_transferencias_vencidas, preparar_pago_transferencia
from backend.logica.pagos_contraentrega import preparar_pago_contraentrega, validar_producto_para_contraentrega

CUENTAS = "bank_accounts"
ORDENES = "orders"
CARRITO = "cart"
PRODUCTOS = "products"

def _money(value: Any, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="INVALID_AMOUNT")
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise HTTPException(status_code=409, detail="INVALID_AMOUNT")
    return amount


def _coupon_discount(db: Any, code: str, subtotal: Decimal) -> Decimal:
    if not code:
        return Decimal("0")
    from backend.logica.cupones import calcular_descuento_cupon
    _, discount = calcular_descuento_cupon(db, code, subtotal)
    return discount


def crear_orden_pago(db: Any, user: dict, data: dict) -> dict:
    liberar_transferencias_vencidas(db)
    method = str(data.get("paymentMethod") or "").strip().lower()
    if method not in ("bank_transfer", "cash_on_delivery"):
        raise HTTPException(status_code=400, detail="INVALID_PAYMENT_METHOD")
    preparadores = {
        "bank_transfer": preparar_pago_transferencia,
        "cash_on_delivery": preparar_pago_contraentrega,
    }
    payment_details = preparadores[method](db, data, datetime.now(timezone.utc))

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
    selected_cart_ids = [entry["_id"] for entry in selected_cart]
    cart = selected_cart

    items, subtotal, shipping = [], Decimal("0"), Decimal("0.00")
    for entry in cart:
        product_id, qty = str(entry.get("productId") or ""), entry.get("quantity")
        if not product_id or isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
        product = db[PRODUCTOS].find_one({"_id": product_id})
        if product is None:
            raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
        if method == "cash_on_delivery":
            validar_producto_para_contraentrega(product)
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
                      "priceDOP": float(price), "quantity": qty,
                      "shippingMethodId": ship_method.get("id", "") if ship_method else "",
                      "shippingMethodName": ship_method.get("name", "") if ship_method else "",
                      "shippingPriceDOP": float(ship_price),
                      "selectedSize": entry.get("selectedSize"), "selectedColor": entry.get("selectedColor")})
    coupon_code = str(data.get("couponCode") or "").strip().upper()
    discount = _coupon_discount(db, coupon_code, subtotal)
    total = subtotal - discount + shipping
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
            "subtotalDOP": float(subtotal), "shippingTotalDOP": float(shipping),
            "couponCode": coupon_code, "couponDiscountDOP": float(discount),
            "total": float(total), "totalDOP": float(total), "currency": "DOP",
            "paymentMethod": method,
            **payment_details,
            "paymentProofUrl": "", "createdAt": now, "updatedAt": now,
            "inventoryReserved": True,
        }
        if not order["customerName"] or not order["address"] or not order["city"] or not order["phone"]:
            raise HTTPException(status_code=400, detail="DELIVERY_FIELDS_REQUIRED")
        db[ORDENES].insert_one(order)
        # Solo se retiran del carrito las filas exactas incluidas en esta orden.
        db[CARRITO].delete_many({"userId": user_id, "_id": {"$in": selected_cart_ids}})
        order.pop("_id", None)
        return {"success": True, "order": {"id": order_id, **order}}
    except Exception:
        if order_id:
            db[ORDENES].delete_one({"_id": order_id})
        # Si Mongo falla durante la retirada, restaurar cualquier fila seleccionada
        # que alcanzara a borrarse antes del error.
        for entry in selected_cart:
            if db[CARRITO].find_one({"_id": entry["_id"], "userId": user_id}) is None:
                db[CARRITO].insert_one(entry)
        for item in reserved:
            db[PRODUCTOS].update_one({"_id": item["productId"]}, {"$inc": {"stock": item["quantity"]}})
        raise
