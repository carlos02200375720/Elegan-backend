import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.collection import Collection

NOMBRE_COLECCION_MENSAJES = "supportMessages"


def coleccion_mensajes(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_MENSAJES]


def inicializar_indices_mensajes(db: Any) -> None:
    coleccion_mensajes(db).create_index(
        [("userId", 1), ("createdAt", 1)],
        name="idx_support_messages_user_created_at",
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
    coleccion_mensajes(db).insert_one(mensaje)
    return {"id": mensaje_id}
