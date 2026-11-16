import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection

from backend.logica.media import eliminar_medios_sin_referencias

NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_productos(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_PRODUCTOS]


def inicializar_indices_productos(db: Any) -> None:
    # Acelera el orden descendente utilizado por el catálogo móvil y el panel.
    coleccion_productos(db).create_index(
        [("createdAt", DESCENDING)],
        name="idx_products_created_at",
    )


def formatear_producto(documento: dict | None) -> dict | None:
    if documento is None:
        return None
    producto = dict(documento)
    producto["id"] = str(producto.pop("_id"))
    # Compatibilidad con documentos anteriores al campo de publicación.
    producto.setdefault("isActive", False)
    return producto


def listar_productos(db: Any, solo_publicados: bool = False) -> dict:
    filtro = {"isActive": True} if solo_publicados else {}
    productos = coleccion_productos(db).find(filtro).sort("createdAt", -1)
    return {"items": [formatear_producto(item) for item in productos]}


def obtener_producto(
    db: Any, product_id: str, solo_publicados: bool = False
) -> dict:
    filtro = {"_id": product_id}
    if solo_publicados:
        filtro["isActive"] = True
    item = coleccion_productos(db).find_one(filtro)
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
    datos.setdefault("isActive", False)
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
    coleccion = coleccion_productos(db)
    anterior = coleccion.find_one({"_id": product_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    resultado = coleccion.update_one({"_id": product_id}, {"$set": datos})
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}


def eliminar_producto(db: Any, product_id: str) -> dict:
    coleccion = coleccion_productos(db)
    anterior = coleccion.find_one({"_id": product_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    coleccion.delete_one({"_id": product_id})
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}
