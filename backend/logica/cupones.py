from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException
from pymongo import ASCENDING

COLECCION_CUPONES = "coupons"
CENTAVO = Decimal("0.01")


def inicializar_indices_cupones(db: Any) -> None:
    db[COLECCION_CUPONES].create_index(
        [("code", ASCENDING)], unique=True, name="idx_coupons_code"
    )
    db[COLECCION_CUPONES].create_index(
        [("isActive", ASCENDING)], name="idx_coupons_active"
    )


def _importe(valor: Any) -> Decimal:
    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE")
    if not importe.is_finite() or importe <= 0:
        raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE")
    return importe.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatear_cupon(documento: dict) -> dict:
    cupon = dict(documento)
    cupon["id"] = str(cupon.pop("_id"))
    return cupon


def listar_cupones(db: Any) -> dict:
    filas = db[COLECCION_CUPONES].find({}).sort("createdAt", -1)
    return {"items": [formatear_cupon(fila) for fila in filas]}


def crear_cupon(db: Any, datos: dict) -> dict:
    codigo = str(datos.get("code") or "").strip().upper()
    tipo = datos.get("discountType")
    valor = _importe(datos.get("discountValue"))
    if tipo == "percentage" and valor > 100:
        raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE")
    ahora = datetime.now(timezone.utc)
    cupon = {
        "_id": codigo,
        "code": codigo,
        "discountType": tipo,
        "discountValue": float(valor),
        "isActive": bool(datos.get("isActive", True)),
        "createdAt": ahora,
        "updatedAt": ahora,
    }
    try:
        db[COLECCION_CUPONES].insert_one(cupon)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="COUPON_ALREADY_EXISTS") from error
        raise
    return {"id": codigo}


def actualizar_cupon(db: Any, codigo: str, datos: dict) -> dict:
    codigo = codigo.strip().upper()
    datos = {key: value for key, value in datos.items() if value is not None}
    if "discountValue" in datos:
        valor = _importe(datos["discountValue"])
        tipo = datos.get("discountType")
        if tipo is None:
            actual = db[COLECCION_CUPONES].find_one({"_id": codigo})
            tipo = actual.get("discountType") if actual else None
        if tipo == "percentage" and valor > 100:
            raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE")
        datos["discountValue"] = float(valor)
    if "discountType" in datos and datos["discountType"] == "percentage":
        actual = db[COLECCION_CUPONES].find_one({"_id": codigo})
        valor = datos.get("discountValue", actual.get("discountValue") if actual else 0)
        if Decimal(str(valor)) > 100:
            raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE")
    datos["updatedAt"] = datetime.now(timezone.utc)
    resultado = db[COLECCION_CUPONES].update_one({"_id": codigo}, {"$set": datos})
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="COUPON_NOT_FOUND")
    return {"success": True}


def eliminar_cupon(db: Any, codigo: str) -> dict:
    resultado = db[COLECCION_CUPONES].delete_one({"_id": codigo.strip().upper()})
    if not resultado.deleted_count:
        raise HTTPException(status_code=404, detail="COUPON_NOT_FOUND")
    return {"success": True}


def calcular_descuento_cupon(db: Any, codigo: str, subtotal: Decimal) -> tuple[dict, Decimal]:
    codigo = str(codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(status_code=400, detail="COUPON_CODE_REQUIRED")
    cupon = db[COLECCION_CUPONES].find_one({"_id": codigo, "isActive": True})
    if cupon is None:
        raise HTTPException(status_code=404, detail="COUPON_INVALID_OR_INACTIVE")
    tipo = cupon.get("discountType")
    valor = _importe(cupon.get("discountValue"))
    if tipo == "percentage":
        if valor > 100:
            raise HTTPException(status_code=409, detail="INVALID_COUPON_CONFIGURATION")
        descuento = subtotal * valor / Decimal("100")
    elif tipo == "fixed":
        descuento = valor
    else:
        raise HTTPException(status_code=409, detail="INVALID_COUPON_CONFIGURATION")
    descuento = min(descuento, subtotal).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return cupon, descuento


def validar_cupon_cliente(db: Any, codigo: str, user_id: str) -> dict:
    carrito = list(db["cart"].find({"userId": str(user_id)}))
    if not carrito:
        raise HTTPException(status_code=400, detail="CART_EMPTY")
    subtotal = Decimal("0.00")
    for item in carrito:
        cantidad = item.get("quantity")
        product_id = str(item.get("productId") or "")
        if not product_id or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 1:
            raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
        producto = db["products"].find_one({"_id": product_id})
        if producto is None:
            raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
        subtotal += _importe(producto.get("price")) * cantidad
    subtotal = subtotal.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    cupon, descuento = calcular_descuento_cupon(db, codigo, subtotal)
    return {
        "valid": True,
        "code": cupon["code"],
        "discountType": cupon["discountType"],
        "discountValue": cupon["discountValue"],
        "discountAmountDOP": format(descuento, ".2f"),
        "subtotalDOP": format(subtotal, ".2f"),
        "totalAfterDiscountDOP": format(subtotal - descuento, ".2f"),
    }
