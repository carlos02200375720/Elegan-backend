import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.servicios.media import eliminar_medios_sin_referencias
from pymongo.collection import Collection

NOMBRE_COLECCION_ANUNCIOS = "announcements"


def coleccion_anuncios(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_ANUNCIOS]


def formatear_anuncio(documento: dict | None) -> dict | None:
    if documento is None:
        return None
    anuncio = dict(documento)
    anuncio["id"] = str(anuncio.pop("_id"))
    return anuncio


def listar_anuncios(db: Any) -> dict:
    documentos = (
        coleccion_anuncios(db)
        .find({"isActive": True})
        .sort("createdAt", -1)
    )
    return {"items": [formatear_anuncio(item) for item in documentos]}


def crear_anuncio(db: Any, datos: dict) -> dict:
    titulo = str(datos.get("title") or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="INVALID_ANNOUNCEMENT")

    ahora = datetime.now(timezone.utc)
    anuncio_id = str(datos.pop("id", None) or uuid.uuid4())
    datos.pop("_id", None)
    datos.pop("userId", None)
    datos.pop("role", None)
    datos.pop("createdAt", None)
    datos.pop("updatedAt", None)

    anuncio = {
        **datos,
        "_id": anuncio_id,
        "title": titulo,
        "description": str(datos.get("description") or "").strip(),
        "imageUrl": str(datos.get("imageUrl") or "").strip(),
        "tag": str(datos.get("tag") or "").strip(),
        "discount": datos.get("discount", ""),
        "isActive": datos.get("isActive", True),
        "createdAt": ahora,
        "updatedAt": ahora,
    }
    try:
        coleccion_anuncios(db).insert_one(anuncio)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="ANNOUNCEMENT_ALREADY_EXISTS")
        raise
    return {"id": anuncio_id}


def actualizar_anuncio(db: Any, anuncio_id: str, datos: dict) -> dict:
    for campo in ("_id", "id", "userId", "role", "createdAt", "updatedAt"):
        datos.pop(campo, None)

    if "title" in datos and datos["title"] is not None:
        datos["title"] = str(datos["title"]).strip()
        if not datos["title"]:
            raise HTTPException(status_code=400, detail="INVALID_ANNOUNCEMENT")

    datos = {key: value for key, value in datos.items() if value is not None}
    datos["updatedAt"] = datetime.now(timezone.utc)
    coleccion = coleccion_anuncios(db)
    anterior = coleccion.find_one({"_id": anuncio_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="ANNOUNCEMENT_NOT_FOUND")
    resultado = coleccion.update_one({"_id": anuncio_id}, {"$set": datos})
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="ANNOUNCEMENT_NOT_FOUND")
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}


def eliminar_anuncio(db: Any, anuncio_id: str) -> dict:
    coleccion = coleccion_anuncios(db)
    anterior = coleccion.find_one({"_id": anuncio_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="ANNOUNCEMENT_NOT_FOUND")
    coleccion.delete_one({"_id": anuncio_id})
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}
