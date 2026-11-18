from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING
from pymongo.collection import Collection

NOMBRE_COLECCION_GUARDADAS = "guardadas"


def coleccion_guardadas(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_GUARDADAS]


def inicializar_indices_guardadas(db: Any) -> None:
    coleccion = coleccion_guardadas(db)
    coleccion.create_index(
        [("userId", 1), ("productId", 1)],
        unique=True,
        name="idx_guardadas_user_product_unique",
    )
    coleccion.create_index(
        [("productId", 1)], name="idx_guardadas_product_id"
    )
    coleccion.create_index(
        [("userId", 1)], name="idx_guardadas_user_id"
    )
    coleccion.create_index(
        [("createdAt", DESCENDING)], name="idx_guardadas_created_at"
    )


def listar_productos_guardados(db: Any, user: dict) -> dict:
    user_id = str(user["_id"])
    filas = coleccion_guardadas(db).find(
        {"userId": user_id}, {"_id": 0, "productId": 1}
    )
    return {"ids": [fila["productId"] for fila in filas]}


def obtener_conteos_guardados(db: Any, product_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(
        str(value).strip() for value in product_ids if str(value).strip()
    ))
    if not ids:
        return {"counts": {}}

    resultados = coleccion_guardadas(db).aggregate(
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


def cambiar_producto_guardado(
    db: Any, user: dict, product_id: str, saved: bool | None
) -> dict:
    user_id = str(user["_id"])
    product_id = str(product_id).strip()
    if not product_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    filtro = {"userId": user_id, "productId": product_id}
    guardar = saved is not False
    coleccion = coleccion_guardadas(db)

    if not guardar:
        coleccion.delete_one(filtro)
    else:
        coleccion.update_one(
            filtro,
            {
                "$setOnInsert": {
                    **filtro,
                    "createdAt": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    return {
        "saved": guardar,
        "savesCount": coleccion.count_documents({"productId": product_id}),
    }
