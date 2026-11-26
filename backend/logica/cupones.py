from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from backend.logica.moneda import formatear_moneda, validar_importe_entero
from pymongo import ASCENDING

COLECCION_CUPONES = "coupons"


def inicializar_indices_cupones(db: Any) -> None:
    db[COLECCION_CUPONES].create_index(
        [("code", ASCENDING)], unique=True, name="idx_coupons_code"
    )
    db[COLECCION_CUPONES].create_index(
        [("isActive", ASCENDING)], name="idx_coupons_active"
    )


def _importe(valor: Any) -> int:
    try:
        return validar_importe_entero(valor, permitir_cero=False)
    except HTTPException as error:
        raise HTTPException(status_code=400, detail="INVALID_COUPON_VALUE") from error


def formatear_cupon(documento: dict) -> dict:
    cupon = dict(documento)
    cupon["id"] = str(cupon.pop("_id"))
    if cupon.get("discountType") == "fixed" and "discountValue" in cupon:
        cupon["discountValueFormatted"] = formatear_moneda(cupon["discountValue"])
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
        "discountValue": valor,
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
        datos["discountValue"] = valor
    if "discountType" in datos and datos["discountType"] == "percentage":
        actual = db[COLECCION_CUPONES].find_one({"_id": codigo})
        valor = datos.get("discountValue", actual.get("discountValue") if actual else 0)
        if type(valor) is not int or valor > 100:
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


def calcular_descuento_cupon(db: Any, codigo: str, subtotal: int, session: Any = None) -> tuple[dict, int]:
    codigo = str(codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(status_code=400, detail="COUPON_CODE_REQUIRED")
    cupon = db[COLECCION_CUPONES].find_one({"_id": codigo, "isActive": True}, session=session)
    if cupon is None:
        raise HTTPException(status_code=404, detail="COUPON_INVALID_OR_INACTIVE")
    tipo = cupon.get("discountType")
    valor = _importe(cupon.get("discountValue"))
    if tipo == "percentage":
        if valor > 100:
            raise HTTPException(status_code=409, detail="INVALID_COUPON_CONFIGURATION")
        numerador = subtotal * valor
        # Importes no negativos: redondeo convencional al entero más cercano.
        descuento = (numerador + 50) // 100
    elif tipo == "fixed":
        descuento = valor
    else:
        raise HTTPException(status_code=409, detail="INVALID_COUPON_CONFIGURATION")
    descuento = min(descuento, subtotal)
    return cupon, descuento


def validar_cupon_cliente(
    db: Any, codigo: str, user_id: str, selected_cart_item_ids: list[str] | None = None
) -> dict:
    carrito = list(db["cart"].find({"userId": str(user_id)}))
    if not carrito:
        raise HTTPException(status_code=400, detail="CART_EMPTY")
    if selected_cart_item_ids is not None:
        if not selected_cart_item_ids or len(set(selected_cart_item_ids)) != len(selected_cart_item_ids):
            raise HTTPException(status_code=400, detail="INVALID_CART_ITEMS_SELECTION")
        selected = set(selected_cart_item_ids)
        carrito_seleccionado = [item for item in carrito if str(item.get("_id")) in selected]
        if len(carrito_seleccionado) != len(selected):
            raise HTTPException(status_code=409, detail="CART_ITEMS_CHANGED")
        carrito = carrito_seleccionado
    subtotal = 0
    for item in carrito:
        cantidad = item.get("quantity")
        product_id = str(item.get("productId") or "")
        if not product_id or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 1:
            raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
        producto = db["products"].find_one({"_id": product_id})
        if producto is None:
            raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
        subtotal += _importe(producto.get("price")) * cantidad
    cupon, descuento = calcular_descuento_cupon(db, codigo, subtotal)
    return {
        "valid": True,
        "code": cupon["code"],
        "discountType": cupon["discountType"],
        "discountValue": cupon["discountValue"],
        "discountAmountDOP": formatear_moneda(descuento),
        "subtotalDOP": formatear_moneda(subtotal),
        "totalAfterDiscountDOP": formatear_moneda(subtotal - descuento),
    }
