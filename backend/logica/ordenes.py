import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from backend.logica.moneda import formatear_moneda
from pymongo import DESCENDING
from pymongo.collection import Collection

from backend.logica.paginacion import obtener_pagina

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


def formatear_orden(documento: dict) -> dict:
    orden = dict(documento)
    orden["id"] = str(orden.pop("_id"))
    for campo in ("subtotalDOP", "shippingTotalDOP", "couponDiscountDOP", "total", "totalDOP"):
        if campo in orden:
            orden[campo + "Formatted"] = formatear_moneda(orden[campo])
    items = orden.get("items")
    if isinstance(items, list):
        orden["items"] = [
            {**item,
             **({"priceFormatted": formatear_moneda(item["priceDOP"])} if "priceDOP" in item else {}),
             **({"shippingPriceFormatted": formatear_moneda(item["shippingPriceDOP"])} if "shippingPriceDOP" in item else {})}
            if isinstance(item, dict) else item
            for item in items
        ]
    return orden


def listar_ordenes(
    db: Any, user: dict, solo_usuario: bool,
    limit: int = 50, cursor: str | None = None,
) -> dict:
    filtro = {"userId": str(user["_id"])} if solo_usuario else {}
    pagina = obtener_pagina(
        coleccion_ordenes(db), filtro, limit=limit, cursor=cursor, direccion=-1
    )
    return {
        "items": [formatear_orden(fila) for fila in pagina["documents"]],
        "hasMore": pagina["hasMore"],
        "nextCursor": pagina["nextCursor"],
    }


def actualizar_estado_orden(db: Any, order_id: str, status: str) -> dict:
    def ejecutar(session: Any) -> dict:
        coleccion = coleccion_ordenes(db)
        existente = coleccion.find_one({"_id": order_id}, session=session)
        if existente is None:
            raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
        if status != "cancelado" and existente.get("paymentMethod") == "bank_transfer" and existente.get("paymentStatus") != "verified":
            raise HTTPException(status_code=409, detail="TRANSFER_NOT_VERIFIED")
        if status != "cancelado" and existente.get("paymentStatus") in ("pending", "awaiting_proof", "proof_submitted", "proof_rejected"):
            raise HTTPException(status_code=409, detail="ORDER_PAYMENT_PENDING")

        now = datetime.now(timezone.utc)
        changes = {"status": status, "updatedAt": now}
        release_stock = status == "cancelado" and existente.get("inventoryReserved") is True
        if release_stock:
            changes.update({
                "inventoryReserved": False,
                "reservationStatus": "released",
                "inventoryReleasedAt": now,
            })
        elif status in ("enviado", "entregado"):
            changes.update({
                "inventoryReserved": False,
                "reservationStatus": "consumed",
            })

        result = coleccion.update_one(
            {"_id": order_id, "status": existente.get("status"),
             "inventoryReserved": existente.get("inventoryReserved", False)},
            {"$set": changes},
            session=session,
        )
        if not result.modified_count:
            raise HTTPException(status_code=409, detail="ORDER_STATE_CHANGED")

        if release_stock:
            for item in existente.get("items", []):
                quantity = item.get("quantity")
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                    raise HTTPException(status_code=409, detail="INVALID_ORDER_INVENTORY")
                db["products"].update_one(
                    {"_id": item.get("productId")},
                    {"$inc": {"stock": quantity}},
                    session=session,
                )

        order = coleccion.find_one({"_id": order_id}, session=session)
        return formatear_orden(order)

    with db.client.start_session() as session:
        return session.with_transaction(ejecutar)
