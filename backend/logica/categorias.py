import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import ASCENDING
from pymongo.collection import Collection

NOMBRE_COLECCION_CATEGORIAS = "store_categories"


def coleccion_categorias(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_CATEGORIAS]


def inicializar_indices_categorias(db: Any) -> None:
    coleccion_categorias(db).create_index(
        [("name", ASCENDING)], unique=True, name="idx_store_categories_name"
    )
    coleccion_categorias(db).create_index(
        [("isActive", ASCENDING), ("sortOrder", ASCENDING)],
        name="idx_store_categories_publication_order",
    )


def formatear_categoria(documento: dict | None) -> dict | None:
    if documento is None:
        return None
    categoria = dict(documento)
    categoria["id"] = str(categoria.pop("_id"))
    categoria.setdefault("isActive", False)
    categoria.setdefault("description", "")
    categoria.setdefault("imageUrl", "")
    categoria.setdefault("icon", "category")
    categoria.setdefault("sortOrder", 0)
    return categoria


def listar_categorias(db: Any, solo_publicadas: bool = False) -> dict:
    filtro = {"isActive": True} if solo_publicadas else {}
    documentos = coleccion_categorias(db).find(filtro).sort(
        [("sortOrder", ASCENDING), ("createdAt", ASCENDING)]
    )
    return {"items": [formatear_categoria(item) for item in documentos]}


def crear_categoria(db: Any, datos: dict) -> dict:
    nombre = str(datos.get("name") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="INVALID_CATEGORY")
    ahora = datetime.now(timezone.utc)
    categoria_id = str(datos.pop("id", None) or uuid.uuid4())
    for campo in ("_id", "createdAt", "updatedAt"):
        datos.pop(campo, None)
    item = {
        **datos,
        "_id": categoria_id,
        "name": nombre,
        "description": str(datos.get("description") or "").strip(),
        "imageUrl": str(datos.get("imageUrl") or "").strip(),
        "icon": str(datos.get("icon") or "category").strip(),
        "sortOrder": int(datos.get("sortOrder") or 0),
        "isActive": bool(datos.get("isActive", False)),
        "createdAt": ahora,
        "updatedAt": ahora,
    }
    try:
        coleccion_categorias(db).insert_one(item)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="CATEGORY_ALREADY_EXISTS")
        raise
    return {"id": categoria_id, "item": formatear_categoria(item)}


def actualizar_categoria(db: Any, categoria_id: str, datos: dict) -> dict:
    for campo in ("_id", "id", "createdAt", "updatedAt"):
        datos.pop(campo, None)
    if "name" in datos and datos["name"] is not None:
        datos["name"] = str(datos["name"]).strip()
        if not datos["name"]:
            raise HTTPException(status_code=400, detail="INVALID_CATEGORY")
    datos = {key: value for key, value in datos.items() if value is not None}
    if "description" in datos:
        datos["description"] = str(datos["description"]).strip()
    if "imageUrl" in datos:
        datos["imageUrl"] = str(datos["imageUrl"]).strip()
    datos["updatedAt"] = datetime.now(timezone.utc)
    coleccion = coleccion_categorias(db)
    if coleccion.find_one({"_id": categoria_id}) is None:
        raise HTTPException(status_code=404, detail="CATEGORY_NOT_FOUND")
    try:
        coleccion.update_one({"_id": categoria_id}, {"$set": datos})
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="CATEGORY_ALREADY_EXISTS")
        raise
    return {"success": True}


def eliminar_categoria(db: Any, categoria_id: str) -> dict:
    resultado = coleccion_categorias(db).delete_one({"_id": categoria_id})
    if not resultado.deleted_count:
        raise HTTPException(status_code=404, detail="CATEGORY_NOT_FOUND")
    return {"success": True}
