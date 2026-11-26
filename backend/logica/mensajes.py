import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from backend.logica.paginacion import obtener_pagina

NOMBRE_COLECCION_MENSAJES = "supportMessages"
DIAS_RETENCION_CONVERSACION = 30


def _fecha_expiracion(ahora: datetime) -> datetime:
    return ahora + timedelta(days=DIAS_RETENCION_CONVERSACION)


def coleccion_mensajes(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_MENSAJES]


def inicializar_indices_mensajes(db: Any) -> None:
    coleccion = coleccion_mensajes(db)
    coleccion.create_index(
        [("userId", ASCENDING), ("createdAt", ASCENDING), ("_id", ASCENDING)],
        name="idx_support_messages_user_created_id",
    )
    coleccion.create_index(
        [("createdAt", DESCENDING), ("_id", DESCENDING)],
        name="idx_support_messages_created_id",
    )
    coleccion.create_index(
        [("expiresAt", 1)],
        expireAfterSeconds=0,
        name="ttl_support_messages_expires_at",
    )



def formatear_mensaje(documento: dict) -> dict:
    mensaje = dict(documento)
    mensaje["id"] = str(mensaje.pop("_id"))
    return mensaje


def listar_mensajes(
    db: Any, user: dict, limit: int = 50, cursor: str | None = None
) -> dict:
    pagina = obtener_pagina(
        coleccion_mensajes(db), {"userId": str(user["_id"])},
        limit=limit, cursor=cursor, direccion=1,
    )
    return {
        "items": [formatear_mensaje(item) for item in pagina["documents"]],
        "hasMore": pagina["hasMore"],
        "nextCursor": pagina["nextCursor"],
    }


def listar_mensajes_admin(
    db: Any, user_id: str | None = None,
    limit: int = 50, cursor: str | None = None,
) -> dict:
    coleccion = coleccion_mensajes(db)
    if user_id:
        pagina = obtener_pagina(
            coleccion, {"userId": user_id},
            limit=limit, cursor=cursor, direccion=1,
        )
    else:
        # Conserva el orden histórico del panel: agrupa por cliente y ordena
        # cronológicamente dentro de cada conversación.
        limite = min(100, max(1, int(limit)))
        filtro = {}
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"===")
                posicion = json.loads(raw.decode("utf-8"))
                fecha = datetime.fromisoformat(posicion["createdAt"])
                user_cursor = str(posicion["userId"])
                id_cursor = str(posicion["id"])
                filtro = {"$or": [
                    {"userId": {"$gt": user_cursor}},
                    {"userId": user_cursor, "createdAt": {"$gt": fecha}},
                    {"userId": user_cursor, "createdAt": fecha, "_id": {"$gt": id_cursor}},
                ]}
            except (ValueError, KeyError, TypeError, UnicodeError):
                raise HTTPException(status_code=400, detail="INVALID_PAGE_CURSOR")
        filas = list(
            coleccion.find(filtro)
            .sort([("userId", 1), ("createdAt", 1), ("_id", 1)])
            .limit(limite + 1)
        )
        hay_mas = len(filas) > limite
        documentos = filas[:limite]
        siguiente = None
        if hay_mas and documentos:
            ultimo = documentos[-1]
            token = json.dumps({
                "userId": str(ultimo.get("userId") or ""),
                "createdAt": ultimo["createdAt"].isoformat(),
                "id": str(ultimo["_id"]),
            }, separators=(",", ":")).encode("utf-8")
            siguiente = base64.urlsafe_b64encode(token).decode("ascii").rstrip("=")
        pagina = {"documents": documentos, "hasMore": hay_mas, "nextCursor": siguiente}
    return {
        "items": [formatear_mensaje(item) for item in pagina["documents"]],
        "hasMore": pagina["hasMore"],
        "nextCursor": pagina["nextCursor"],
    }


def _validar_texto(texto: Any) -> str:
    valor = str(texto or "").strip()
    if not valor or len(valor) > 4000:
        raise HTTPException(status_code=400, detail="INVALID_MESSAGE")
    return valor


def crear_mensaje(db: Any, user: dict, datos: dict) -> dict:
    texto = _validar_texto(datos.get("text"))
    user_id = str(user["_id"])
    ahora = datetime.now(timezone.utc)
    mensaje_id = str(uuid.uuid4())
    mensaje = {
        "_id": mensaje_id,
        "userId": user_id,
        "sender": "user",
        "senderName": str(user.get("name") or "Cliente"),
        "text": texto,
        "createdAt": ahora,
    }
    coleccion = coleccion_mensajes(db)
    expiracion = _fecha_expiracion(ahora)
    # Renovar la fecha de expiración de toda la conversación con cada mensaje.
    coleccion.update_many(
        {"userId": user_id},
        {"$set": {"expiresAt": expiracion}},
    )
    mensaje["expiresAt"] = expiracion
    coleccion.insert_one(mensaje)

    return {"id": mensaje_id}


def responder_mensaje_admin(
    db: Any, user_id: str, admin: dict, datos: dict
) -> dict:
    texto = _validar_texto(datos.get("text"))
    # Evita crear conversaciones para identificadores inexistentes.
    if coleccion_mensajes(db).find_one({"userId": user_id}) is None:
        raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND")

    mensaje_id = str(uuid.uuid4())
    mensaje = {
        "_id": mensaje_id,
        "userId": user_id,
        "sender": "support",
        "senderName": str(admin.get("name") or "Elegan Concierge"),
        "text": texto,
        "createdAt": datetime.now(timezone.utc),
    }
    coleccion = coleccion_mensajes(db)
    ahora = mensaje["createdAt"]
    expiracion = _fecha_expiracion(ahora)
    # Un mensaje nuevo de soporte también renueva los 30 días de la conversación.
    coleccion.update_many(
        {"userId": user_id},
        {"$set": {"expiresAt": expiracion}},
    )
    mensaje["expiresAt"] = expiracion
    coleccion.insert_one(mensaje)
    return {"id": mensaje_id}


def migrar_conversaciones_sin_expiracion(db: Any, batch_size: int = 200) -> int:
    """Migra conversaciones antiguas en streaming, fuera del arranque HTTP."""
    coleccion = coleccion_mensajes(db)
    conversaciones = coleccion.aggregate(
        [
            {"$match": {"userId": {"$type": "string", "$ne": ""}}},
            {"$group": {
                "_id": "$userId",
                "ultimaActividad": {"$max": "$createdAt"},
                "pendientes": {"$sum": {"$cond": [
                    {"$eq": [{"$type": "$expiresAt"}, "missing"]}, 1, 0
                ]}},
            }},
            {"$match": {"pendientes": {"$gt": 0}, "ultimaActividad": {"$type": "date"}}},
        ],
        allowDiskUse=True,
    ).batch_size(batch_size)
    procesadas = 0
    for conversacion in conversaciones:
        coleccion.update_many(
            {"userId": conversacion["_id"], "expiresAt": {"$exists": False}},
            {"$set": {"expiresAt": _fecha_expiracion(conversacion["ultimaActividad"])}},
        )
        procesadas += 1
    return procesadas
