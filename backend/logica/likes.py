from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING
from pymongo.collection import Collection

NOMBRE_COLECCION_LIKES = "likes"
NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_likes(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_LIKES]


def inicializar_indices_likes(db: Any) -> None:
    coleccion = coleccion_likes(db)
    coleccion.create_index(
        [("userId", 1), ("productId", 1)],
        unique=True,
        name="idx_likes_user_product_unique",
    )
    coleccion.create_index(
        [("productId", 1), ("createdAt", DESCENDING)],
        name="idx_likes_product_created_at",
    )
    coleccion.create_index(
        [("userId", 1)],
        name="idx_likes_user_id",
    )


def listar_likes_usuario(db: Any, user: dict) -> dict:
    user_id = str(user["_id"])
    filas = coleccion_likes(db).find(
        {"userId": user_id}, {"_id": 0, "productId": 1}
    )
    return {"ids": [fila["productId"] for fila in filas]}


def obtener_conteos_likes(db: Any, product_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(str(value).strip() for value in product_ids if str(value).strip()))
    if not ids:
        return {"counts": {}}

    resultados = coleccion_likes(db).aggregate(
        [
            {"$match": {"productId": {"$in": ids}}},
            {"$group": {"_id": "$productId", "count": {"$sum": 1}}},
        ]
    )
    counts = {product_id: 0 for product_id in ids}
    counts.update({str(item["_id"]): int(item["count"]) for item in resultados})
    return {"counts": counts}


def cambiar_like(db: Any, user: dict, product_id: str, liked: bool) -> dict:
    user_id = str(user["_id"])
    product_id = str(product_id).strip()
    if not product_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one(
        {"_id": product_id, "isActive": True}, {"_id": 1}
    )
    if producto is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    coleccion = coleccion_likes(db)
    filtro = {"userId": user_id, "productId": product_id}
    if liked:
        ahora = datetime.now(timezone.utc)
        try:
            coleccion.update_one(
                filtro,
                {"$setOnInsert": {**filtro, "createdAt": ahora}},
                upsert=True,
            )
        except Exception as error:
            # Dos solicitudes simultáneas del mismo usuario no deben duplicar el like.
            if getattr(error, "code", None) != 11000:
                raise
    else:
        coleccion.delete_one(filtro)

    return {
        "liked": liked,
        "likesCount": coleccion.count_documents({"productId": product_id}),
    }
