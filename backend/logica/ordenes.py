import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from backend.logica.moneda import formatear_moneda
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
    coleccion.create_index(
        [("paymentMethod", 1), ("paymentStatus", 1), ("expiresAt", 1)],
        name="idx_orders_payment_expiration",
    )


def _importe_almacenado(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    texto = valor.strip().replace("RD$", "").replace("$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return Decimal(texto)
    except (InvalidOperation, TypeError, ValueError):
        return valor


def formatear_orden(documento: dict) -> dict:
    orden = dict(documento)
    orden["id"] = str(orden.pop("_id"))
    for campo in ("subtotalDOP", "shippingTotalDOP", "couponDiscountDOP", "total", "totalDOP"):
        if campo in orden:
            orden[campo + "Formatted"] = formatear_moneda(_importe_almacenado(orden[campo]))
    items = orden.get("items")
    if isinstance(items, list):
        orden["items"] = [
            {**item,
             **({"priceFormatted": formatear_moneda(_importe_almacenado(item["priceDOP"]))} if "priceDOP" in item else {}),
             **({"shippingPriceFormatted": formatear_moneda(_importe_almacenado(item["shippingPriceDOP"]))} if "shippingPriceDOP" in item else {})}
            if isinstance(item, dict) else item
            for item in items
        ]
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
    if status != "cancelado" and existente.get("paymentMethod") == "bank_transfer" and existente.get("paymentStatus") != "verified":
        raise HTTPException(status_code=409, detail="TRANSFER_NOT_VERIFIED")
    if status != "cancelado" and existente.get("paymentStatus") in ("pending", "awaiting_proof", "proof_submitted", "proof_rejected"):
        raise HTTPException(status_code=409, detail="ORDER_PAYMENT_PENDING")

    cambios = {"status": status, "updatedAt": datetime.now(timezone.utc)}
    liberar_stock = status == "cancelado" and existente.get("inventoryReserved") is True
    if liberar_stock or status in ("enviado", "entregado"):
        cambios["inventoryReserved"] = False
    resultado = coleccion.update_one({"_id": order_id}, {"$set": cambios})
    if resultado.modified_count and liberar_stock:
        for item in existente.get("items", []):
            coleccion_productos = db["products"]
            coleccion_productos.update_one(
                {"_id": item.get("productId")},
                {"$inc": {"stock": int(item.get("quantity", 0))}},
            )
    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")

    orden = coleccion.find_one({"_id": order_id})
    return formatear_orden(orden)
