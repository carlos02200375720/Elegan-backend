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


def cambiar_producto_guardado(
    db: Any, user: dict, product_id: str, saved: bool | None
) -> dict:
    user_id = str(user["_id"])
    filtro = {"userId": user_id, "productId": str(product_id)}
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

    return {"saved": guardar}
