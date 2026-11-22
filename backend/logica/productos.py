import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo import DESCENDING
from pymongo.collection import Collection

from backend.logica.media import eliminar_medios_sin_referencias

NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_productos(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_PRODUCTOS]


def inicializar_indices_productos(db: Any) -> None:
    # Acelera el orden descendente utilizado por el catálogo móvil y el panel.
    coleccion_productos(db).create_index(
        [("createdAt", DESCENDING)],
        name="idx_products_created_at",
    )


def formatear_producto(documento: dict | None) -> dict | None:
    if documento is None:
        return None
    producto = dict(documento)
    producto["id"] = str(producto.pop("_id"))
    # Compatibilidad con documentos anteriores al campo de publicación.
    producto.setdefault("isActive", False)
    return producto


def listar_productos(
    db: Any,
    solo_publicados: bool = False,
    incluir_conteo_comentarios: bool = False,
) -> dict:
    filtro = {"isActive": True} if solo_publicados else {}
    documentos = list(coleccion_productos(db).find(filtro).sort("createdAt", -1))

    conteos_comentarios: dict[str, int] = {}
    if incluir_conteo_comentarios and documentos:
        ids_productos = [str(item.get("_id", "")) for item in documentos]
        resultados = db["comments"].aggregate(
            [
                {"$match": {"productId": {"$in": ids_productos}}},
                {"$group": {"_id": "$productId", "count": {"$sum": 1}}},
            ]
        )
        conteos_comentarios = {
            str(item["_id"]): int(item["count"]) for item in resultados
        }

    items = []
    for documento in documentos:
        producto = formatear_producto(documento)
        if incluir_conteo_comentarios and producto is not None:
            producto["commentsCount"] = conteos_comentarios.get(
                str(producto["id"]), 0
            )
        items.append(producto)

    return {"items": items}



def _numero_seguro(valor: Any, predeterminado: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return predeterminado


def _puntuacion_recomendacion(producto: dict, producto_base: dict) -> float:
    """Prioriza categoría y precio similares, con señales de calidad del catálogo."""
    categoria_base = str(producto_base.get("category") or "").strip().casefold()
    categoria = str(producto.get("category") or "").strip().casefold()
    misma_categoria = bool(categoria_base) and categoria == categoria_base

    puntuacion = 100.0 if misma_categoria else 0.0
    precio_base = max(0.0, _numero_seguro(producto_base.get("price")))
    precio = max(0.0, _numero_seguro(producto.get("price")))
    if precio_base > 0:
        diferencia = abs(precio - precio_base) / precio_base
        puntuacion += 25.0 * max(0.0, 1.0 - min(diferencia, 1.0))

    if producto.get("isFeatured") is True:
        puntuacion += 8.0
    rating = min(5.0, max(0.0, _numero_seguro(producto.get("rating"))))
    puntuacion += (rating / 5.0) * 6.0
    reviews = max(0.0, _numero_seguro(producto.get("reviewCount")))
    puntuacion += 6.0 * min(reviews / 20.0, 1.0)
    return puntuacion


def recomendar_productos(db: Any, product_id: str, limit: int = 12) -> dict:
    """Devuelve productos publicados, excluye el actual y ordena por relevancia."""
    product_id = str(product_id or "").strip()
    limit = min(30, max(1, int(limit)))
    coleccion = coleccion_productos(db)
    producto_base = coleccion.find_one({"_id": product_id, "isActive": True})
    if producto_base is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    candidatos = list(
        coleccion.find({"isActive": True, "_id": {"$ne": product_id}})
        .sort("createdAt", DESCENDING)
    )
    # El sort de Mongo prioriza los más recientes en empates sin comparar
    # tipos de fecha distintos que puedan existir en documentos históricos.
    candidatos.sort(
        key=lambda item: _puntuacion_recomendacion(item, producto_base),
        reverse=True,
    )
    return {"items": [formatear_producto(item) for item in candidatos[:limit]]}


def obtener_producto(
    db: Any, product_id: str, solo_publicados: bool = False
) -> dict:
    filtro = {"_id": product_id}
    if solo_publicados:
        filtro["isActive"] = True
    item = coleccion_productos(db).find_one(filtro)
    if item is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    return {"item": formatear_producto(item)}


def crear_producto(db: Any, datos: dict) -> dict:
    nombre = str(datos.get("name") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT")

    ahora = datetime.now(timezone.utc)
    product_id = str(datos.pop("id", None) or uuid.uuid4())
    datos.pop("_id", None)
    datos.pop("createdAt", None)
    datos.pop("updatedAt", None)
    datos.setdefault("isActive", False)
    item = {
        **datos,
        "_id": product_id,
        "name": nombre,
        "createdAt": ahora,
        "updatedAt": ahora,
    }
    try:
        coleccion_productos(db).insert_one(item)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="PRODUCT_ALREADY_EXISTS")
        raise
    return {"id": product_id, "item": formatear_producto(item)}


def actualizar_producto(db: Any, product_id: str, datos: dict) -> dict:
    datos.pop("id", None)
    datos.pop("_id", None)
    datos.pop("createdAt", None)
    datos.pop("updatedAt", None)
    if "name" in datos and datos["name"] is not None:
        datos["name"] = str(datos["name"]).strip()
        if not datos["name"]:
            raise HTTPException(status_code=400, detail="INVALID_PRODUCT")
    datos = {key: value for key, value in datos.items() if value is not None}
    datos["updatedAt"] = datetime.now(timezone.utc)
    coleccion = coleccion_productos(db)
    anterior = coleccion.find_one({"_id": product_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    resultado = coleccion.update_one({"_id": product_id}, {"$set": datos})
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}


def eliminar_producto(db: Any, product_id: str) -> dict:
    coleccion = coleccion_productos(db)
    anterior = coleccion.find_one({"_id": product_id})
    if anterior is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    # Eliminar únicamente las interacciones asociadas al producto.
    # Los pedidos se conservan íntegros como historial de compras.
    db["likes"].delete_many({"productId": product_id})
    db["comments"].delete_many({"productId": product_id})
    db["publication_shares"].delete_many({"productId": product_id})
    db["guardadas"].delete_many({"productId": product_id})
    db["cart"].delete_many({"productId": product_id})

    coleccion.delete_one({"_id": product_id})
    eliminar_medios_sin_referencias(db, [anterior])
    return {"success": True}
