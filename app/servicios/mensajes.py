import uuid
from datetime import datetime, timedelta, timezone
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


def _respuesta_automatica(texto: str) -> str:
    normalizado = texto.lower()
    if "envio" in normalizado or "entrega" in normalizado:
        return (
            "Gracias por tu consulta. Nuestro equipo de Elegan te ayudará "
            "con la información de entrega de tu pedido."
        )
    if "talla" in normalizado or "medida" in normalizado:
        return (
            "Gracias por escribirnos. Nuestro equipo puede orientarte "
            "con las tallas y medidas disponibles."
        )
    if "devolucion" in normalizado or "cambio" in normalizado:
        return (
            "Recibimos tu consulta sobre cambios o devoluciones. "
            "Un asesor de Elegan te dará seguimiento."
        )
    if "descuento" in normalizado or "promocion" in normalizado:
        return (
            "Gracias por consultar nuestras promociones. Revisa los "
            "anuncios y ofertas vigentes en la tienda."
        )
    return (
        "Gracias por comunicarte con Elegan. Hemos recibido tu consulta "
        "y nuestro equipo te dará seguimiento."
    )


def crear_mensaje(db: Any, user: dict, datos: dict) -> dict:
    texto = str(datos.get("text") or "").strip()
    if not texto or len(texto) > 4000:
        raise HTTPException(status_code=400, detail="INVALID_MESSAGE")

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

    respuesta = {
        "_id": str(uuid.uuid4()),
        "userId": user_id,
        "sender": "support",
        "senderName": "Elegan Concierge",
        "text": _respuesta_automatica(texto),
        "createdAt": ahora + timedelta(milliseconds=1),
    }
    coleccion.insert_one(respuesta)
    return {"id": mensaje_id}
