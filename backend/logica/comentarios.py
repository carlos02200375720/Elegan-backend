from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection


NOMBRE_COLECCION_COMENTARIOS = "comments"
NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_comentarios(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_COMENTARIOS]


def inicializar_indices_comentarios(db: Any) -> None:
    coleccion = coleccion_comentarios(db)
    coleccion.create_index(
        [("productId", 1), ("createdAt", DESCENDING)],
        name="idx_comments_product_created_at",
    )
    coleccion.create_index(
        [("userId", 1), ("createdAt", DESCENDING)],
        name="idx_comments_user_created_at",
    )


def _validar_producto_publicado(db: Any, product_id: str) -> str:
    clean_id = str(product_id).strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one(
        {"_id": clean_id, "isActive": True}, {"_id": 1}
    )
    if producto is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    return clean_id


def _comentario_publico(documento: dict) -> dict:
    return {
        "id": str(documento.get("_id", "")),
        "productId": str(documento.get("productId", "")),
        "userId": str(documento.get("userId", "")),
        "displayName": str(documento.get("displayName", "Cliente")),
        "text": str(documento.get("text", "")),
        "createdAt": documento.get("createdAt"),
    }


def listar_comentarios(db: Any, product_id: str, user_id: str = "") -> dict:
    clean_id = _validar_producto_publicado(db, product_id)
    coleccion = coleccion_comentarios(db)
    blocked_ids = [
        str(item.get("blockedUserId", ""))
        for item in db["blocked_users"].find(
            {"userId": user_id}, {"blockedUserId": 1}
        )
    ] if user_id else []
    filtro = {"productId": clean_id, "userId": {"$nin": blocked_ids}}
    documentos = coleccion.find(filtro).sort("createdAt", DESCENDING).limit(200)

    items = [_comentario_publico(item) for item in documentos]
    return {
        "items": items,
        "commentsCount": coleccion.count_documents(filtro),
    }


def crear_comentario(db: Any, user: dict, product_id: str, text: str) -> dict:
    clean_id = _validar_producto_publicado(db, product_id)
    clean_text = str(text).strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="EMPTY_COMMENT")
    if len(clean_text) > 1000:
        raise HTTPException(status_code=422, detail="COMMENT_TOO_LONG")

    documento = {
        "_id": str(uuid.uuid4()),
        "productId": clean_id,
        "userId": str(user["_id"]),
        "displayName": str(user.get("name") or "Cliente").strip()[:80] or "Cliente",
        "text": clean_text,
        "createdAt": datetime.now(timezone.utc),
    }
    coleccion = coleccion_comentarios(db)
    coleccion.insert_one(documento)

    return {
        "item": _comentario_publico(documento),
        "commentsCount": coleccion.count_documents({"productId": clean_id}),
    }
