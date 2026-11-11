import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.collection import Collection

NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_productos(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_PRODUCTOS]


def formatear_producto(documento: dict | None) -> dict | None:
    if documento is None:
        return None
    producto = dict(documento)
    producto["id"] = str(producto.pop("_id"))
    return producto


def listar_productos(db: Any) -> dict:
    productos = coleccion_productos(db).find({}).sort("createdAt", -1)
    return {"items": [formatear_producto(item) for item in productos]}


def obtener_producto(db: Any, product_id: str) -> dict:
    item = coleccion_productos(db).find_one({"_id": product_id})
    if item is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    return {"item": formatear_producto(item)}


def crear_producto(db: Any, datos: dict) -> dict:
    nombre = str(datos.get("name") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT")

    ahora = datetime.now(timezone.utc)
    product_id = str(datos.pop("id", None) or uuid.uuid4())
    datos.pop("_id", None)
    datos.pop("createdAt", None)
    datos.pop("updatedAt", None)
    item = {
        **datos,
        "_id": product_id,
        "name": nombre,
        "createdAt": ahora,
        "updatedAt": ahora,
    }
    try:
        coleccion_productos(db).insert_one(item)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="PRODUCT_ALREADY_EXISTS")
        raise
    return {"id": product_id, "item": formatear_producto(item)}


def actualizar_producto(db: Any, product_id: str, datos: dict) -> dict:
    datos.pop("id", None)
    datos.pop("_id", None)
    datos.pop("createdAt", None)
    datos.pop("updatedAt", None)
    if "name" in datos and datos["name"] is not None:
        datos["name"] = str(datos["name"]).strip()
        if not datos["name"]:
            raise HTTPException(status_code=400, detail="INVALID_PRODUCT")
    datos = {key: value for key, value in datos.items() if value is not None}
    datos["updatedAt"] = datetime.now(timezone.utc)
    resultado = coleccion_productos(db).update_one(
        {"_id": product_id}, {"$set": datos}
    )
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    return {"success": True}


def eliminar_producto(db: Any, product_id: str) -> dict:
    coleccion_productos(db).delete_one({"_id": product_id})
    return {"success": True}
