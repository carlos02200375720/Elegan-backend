import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.collection import Collection

NOMBRE_COLECCION_MENSAJES = "supportMessages"
DIAS_RETENCION_CONVERSACION = 30


def _fecha_expiracion(ahora: datetime) -> datetime:
    return ahora + timedelta(days=DIAS_RETENCION_CONVERSACION)


def coleccion_mensajes(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_MENSAJES]


def inicializar_indices_mensajes(db: Any) -> None:
    coleccion = coleccion_mensajes(db)
    coleccion.create_index(
        [("userId", 1), ("createdAt", 1)],
        name="idx_support_messages_user_created_at",
    )
    coleccion.create_index(
        [("expiresAt", 1)],
        expireAfterSeconds=0,
        name="ttl_support_messages_expires_at",
    )

    # Migra mensajes existentes: todos los mensajes de cada conversación
    # vencen 30 días después de su actividad más reciente.
    conversaciones_pendientes = coleccion.aggregate([
        {"$match": {"expiresAt": {"$exists": False}}},
        {"$group": {"_id": "$userId"}},
    ])
    for conversacion in conversaciones_pendientes:
        user_id = conversacion.get("_id")
        if not user_id:
            continue
        ultimo_mensaje = coleccion.find_one(
            {"userId": user_id},
            sort=[("createdAt", -1)],
            projection={"createdAt": 1},
        )
        ultima_actividad = (ultimo_mensaje or {}).get("createdAt")
        if isinstance(ultima_actividad, datetime):
            coleccion.update_many(
                {"userId": user_id},
                {"$set": {"expiresAt": _fecha_expiracion(ultima_actividad)}},
            )


def formatear_mensaje(documento: dict) -> dict:
    mensaje = dict(documento)
    mensaje["id"] = str(mensaje.pop("_id"))
    return mensaje


def listar_mensajes(db: Any, user: dict) -> dict:
    user_id = str(user["_id"])
    mensajes = (
        coleccion_mensajes(db)
        .find({"userId": user_id})
        .sort("createdAt", 1)
    )
    return {"items": [formatear_mensaje(item) for item in mensajes]}


def listar_mensajes_admin(db: Any, user_id: str | None = None) -> dict:
    filtro = {"userId": user_id} if user_id else {}
    mensajes = (
        coleccion_mensajes(db)
        .find(filtro)
        .sort([("userId", 1), ("createdAt", 1)])
    )
    return {"items": [formatear_mensaje(item) for item in mensajes]}


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
