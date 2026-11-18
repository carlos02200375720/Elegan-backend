from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection

NOMBRE_COLECCION_COMPARTIDOS = "publication_shares"
NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_compartidos(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_COMPARTIDOS]


def inicializar_indices_compartidos(db: Any) -> None:
    coleccion = coleccion_compartidos(db)
    coleccion.create_index(
        [("productId", 1), ("createdAt", DESCENDING)],
        name="idx_shares_product_created_at",
    )
    coleccion.create_index(
        [("userId", 1), ("createdAt", DESCENDING)],
        name="idx_shares_user_created_at",
    )


def obtener_conteos_compartidos(db: Any, product_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(
        str(value).strip() for value in product_ids if str(value).strip()
    ))
    if not ids:
        return {"counts": {}}

    resultados = coleccion_compartidos(db).aggregate(
        [
            {"$match": {"productId": {"$in": ids}}},
            {"$group": {"_id": "$productId", "count": {"$sum": 1}}},
        ]
    )
    counts = {product_id: 0 for product_id in ids}
    counts.update({
        str(item["_id"]): int(item["count"]) for item in resultados
    })
    return {"counts": counts}


def registrar_compartido(db: Any, user: dict, product_id: str) -> dict:
    product_id = str(product_id).strip()
    if not product_id:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one(
        {"_id": product_id, "isActive": True}, {"_id": 1}
    )
    if producto is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    coleccion = coleccion_compartidos(db)
    coleccion.insert_one({
        "userId": str(user["_id"]),
        "productId": product_id,
        "createdAt": datetime.now(timezone.utc),
    })
    return {
        "success": True,
        "sharesCount": coleccion.count_documents({"productId": product_id}),
    }
