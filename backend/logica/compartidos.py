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
    coleccion.create_index(
        [("eventId", 1)],
        name="uq_shares_event_id",
        unique=True,
        sparse=True,
    )
    # Compatibilidad temporal con clientes visitantes que aún no envían eventId.
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
    clave_duplicado: dict | None = None

    if user is not None:
        documento["userId"] = str(user["_id"])
    else:
        visitor_id = str(visitor_id or "").strip()
        if not visitor_id or len(visitor_id) > 128:
            raise HTTPException(status_code=422, detail="INVALID_VISITOR_ID")
        documento["visitorId"] = visitor_id
        if not event_id:
            clave_duplicado = {
                "legacyVisitorKey": f"{product_id}:{visitor_id}"
            }
            documento.update(clave_duplicado)

    if event_id:
        event_id = str(event_id).strip()
        if not event_id or len(event_id) > 128:
            raise HTTPException(status_code=422, detail="INVALID_EVENT_ID")
        documento["eventId"] = event_id
        clave_duplicado = {"eventId": event_id}

    coleccion = coleccion_compartidos(db)
    duplicado = False
    try:
        coleccion.insert_one(documento)
    except DuplicateKeyError:
        existente = coleccion.find_one(clave_duplicado or {})
        if existente is None or existente.get("productId") != product_id:
            raise HTTPException(status_code=409, detail="SHARE_EVENT_CONFLICT")
        duplicado = True

    return {
        "success": True,
        "sharesCount": coleccion.count_documents({"productId": product_id}),
        "duplicate": duplicado,
    }
