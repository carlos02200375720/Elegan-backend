from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

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
    # eventId hace idempotente cada solicitud y evita contar reintentos dos veces.
    coleccion.create_index(
        [("eventId", 1)],
        name="uq_shares_event_id",
        unique=True,
        sparse=True,
    )
    # Compatibilidad con clientes visitantes antiguos que aún no envían eventId:
    # se cuenta como máximo un compartido por visitante y producto.
    coleccion.create_index(
        [("legacyVisitorKey", 1)],
        name="uq_shares_legacy_visitor",
        unique=True,
        sparse=True,
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


def registrar_compartido(
    db: Any,
    product_id: str,
    user: dict | None = None,
    visitor_id: str | None = None,
    event_id: str | None = None,
) -> dict:
    product_id = str(product_id).strip()
    if not product_id:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one(
        {"_id": product_id, "isActive": True}, {"_id": 1}
    )
    if producto is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    documento = {
        "productId": product_id,
        "createdAt": datetime.now(timezone.utc),
    }
    if user is not None:
        documento["userId"] = str(user["_id"])
    else:
        visitor_id = str(visitor_id or "").strip()
        if not visitor_id:
            raise HTTPException(status_code=422, detail="VISITOR_ID_REQUIRED")
        documento["visitorId"] = visitor_id
        if not event_id:
            documento["legacyVisitorKey"] = f"{product_id}:{visitor_id}"

    if event_id:
        documento["eventId"] = str(event_id).strip()

    coleccion = coleccion_compartidos(db)
    try:
        coleccion.insert_one(documento)
    except DuplicateKeyError:
        # Un reintento del mismo evento ya fue registrado: responder éxito
        # sin incrementar nuevamente el contador.
        pass

    return {
        "success": True,
        "sharesCount": coleccion.count_documents({"productId": product_id}),
        "duplicate": bool(
            (event_id and coleccion.find_one({"eventId": str(event_id).strip()}, {"_id": 1}))
            or (
                not event_id
                and user is None
                and coleccion.find_one(
                    {"legacyVisitorKey": f"{product_id}:{str(visitor_id).strip()}"},
                    {"_id": 1},
                )
            )
        ),
    }
