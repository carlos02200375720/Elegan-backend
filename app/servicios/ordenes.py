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


def crear_orden(db: Any, user: dict, datos: dict) -> dict:
    nombre = str(datos.get("customerName") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="INVALID_ORDER")

    user_id = str(user["_id"])
    carrito = db[NOMBRE_COLECCION_CARRITO]
    items = list(carrito.find({"userId": user_id}))
    if not items:
        raise HTTPException(status_code=400, detail="CART_EMPTY")

    total = sum(
        (float(item.get("price") or 0) * int(item.get("quantity") or 0))
        for item in items
    )
    cantidad = sum(int(item.get("quantity") or 0) for item in items)
    resumen = ", ".join(
        f"{item.get('name', '')} x{item.get('quantity', 0)}" for item in items
    )

    # Igual que cleanObject del backend anterior: el cliente no puede fijar
    # identificador, propietario, rol ni marcas de tiempo del pedido.
    datos_limpios = dict(datos)
    for campo in ("_id", "userId", "role", "createdAt", "updatedAt",
                  "total", "itemCount", "itemsSummary", "status"):
        datos_limpios.pop(campo, None)

    orden_id = str(uuid.uuid4())
    orden = {
        **datos_limpios,
        "customerName": nombre,
        "total": total,
        "itemCount": cantidad,
        "itemsSummary": resumen,
        "_id": orden_id,
        "userId": user_id,
        "status": "confirmado",
        "createdAt": datetime.now(timezone.utc),
    }

    coleccion_ordenes(db).insert_one(orden)
    carrito.delete_many({"userId": user_id})
    return {"id": orden_id}
