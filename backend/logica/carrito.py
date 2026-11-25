import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from backend.logica.moneda import formatear_moneda
from pymongo.collection import Collection

NOMBRE_COLECCION_CARRITO = "cart"
NOMBRE_COLECCION_PRODUCTOS = "products"


def coleccion_carrito(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_CARRITO]


def inicializar_indices_carrito(db: Any) -> None:
    coleccion = coleccion_carrito(db)
    coleccion.create_index(
        [
            ("userId", 1),
            ("productId", 1),
            ("selectedSize", 1),
            ("selectedColor", 1),
        ("selectedShippingId", 1),
        ],
        name="idx_cart_user_product_variant_shipping",
    )
    coleccion.create_index(
        [("userId", 1), ("createdAt", 1)],
        name="idx_cart_user_created_at",
    )


def formatear_item_carrito(documento: dict) -> dict:
    item = dict(documento)
    item["id"] = str(item.pop("_id"))
    if "price" in item:
        item["priceFormatted"] = formatear_moneda(item["price"])
    if "shippingPrice" in item:
        item["shippingPriceFormatted"] = formatear_moneda(item["shippingPrice"])
    return item


def obtener_carrito(db: Any, user: dict) -> dict:
    user_id = str(user["_id"])
    filas = coleccion_carrito(db).find({"userId": user_id}).sort("createdAt", 1)
    items = []
    for fila in filas:
        producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one({"_id": str(fila.get("productId") or "")})
        fila["allowCashOnDelivery"] = (
            producto.get("allowCashOnDelivery", True) if producto is not None else False
        )
        items.append(formatear_item_carrito(fila))
    return {"items": items}


def agregar_al_carrito(db: Any, user: dict, datos: dict) -> dict:
    user_id = str(user["_id"])
    product_id = str(datos["productId"]).strip()
    if not product_id:
        raise HTTPException(status_code=400, detail="INVALID_PRODUCT_ID")

    producto = db[NOMBRE_COLECCION_PRODUCTOS].find_one({"_id": product_id})
    if producto is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")

    cantidad = datos.get("quantity", 1)
    if isinstance(cantidad, bool) or not isinstance(cantidad, int) or not 1 <= cantidad <= 99:
        raise HTTPException(status_code=400, detail="INVALID_QUANTITY")

    talla = datos.get("selectedSize")
    color = datos.get("selectedColor")
    shipping_id = str(datos.get("selectedShippingId") or "").strip()
    shipping_methods = producto.get("shippingMethods") or []
    metodo_envio = next(
        (metodo for metodo in shipping_methods if str(metodo.get("id") or "") == shipping_id),
        None,
    ) if shipping_id else None
    if shipping_methods and metodo_envio is None:
        raise HTTPException(status_code=400, detail="INVALID_SHIPPING_METHOD")
    if not shipping_methods and shipping_id:
        raise HTTPException(status_code=400, detail="INVALID_SHIPPING_METHOD")
    filtro = {
        "userId": user_id,
        "productId": product_id,
        "selectedSize": talla,
        "selectedColor": color,
        "selectedShippingId": shipping_id,
    }
    ahora = datetime.now(timezone.utc)
    coleccion = coleccion_carrito(db)
    existente = coleccion.find_one(filtro)

    snapshot = {
        "name": producto.get("name", ""),
        "price": producto.get("price", 0),
        "imageUrl": producto.get("imageUrl", ""),
        "shippingMethodId": metodo_envio.get("id") if metodo_envio else "",
        "shippingMethodName": metodo_envio.get("name", "") if metodo_envio else "",
        "shippingPrice": float(metodo_envio.get("price", 0)) if metodo_envio else 0.0,
        "shippingDeliveryTime": metodo_envio.get("deliveryTime", "") if metodo_envio else "",
        "shippingOrigin": metodo_envio.get("origin", "") if metodo_envio else "",
        "allowCashOnDelivery": producto.get("allowCashOnDelivery", True),
    }

    if existente is not None:
        coleccion.update_one(
            {"_id": existente["_id"], "userId": user_id},
            {
                "$inc": {"quantity": cantidad},
                "$set": {**snapshot, "updatedAt": ahora},
            },
        )
        return {"id": str(existente["_id"])}

    item_id = str(uuid.uuid4())
    coleccion.insert_one(
        {
            "_id": item_id,
            **filtro,
            **snapshot,
            "quantity": cantidad,
            "createdAt": ahora,
            "updatedAt": ahora,
        }
    )
    return {"id": item_id}


def actualizar_item_carrito(
    db: Any, user: dict, item_id: str, quantity: int
) -> dict:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
        raise HTTPException(status_code=400, detail="INVALID_QUANTITY")

    resultado = coleccion_carrito(db).update_one(
        {"_id": str(item_id), "userId": str(user["_id"])},
        {"$set": {"quantity": quantity, "updatedAt": datetime.now(timezone.utc)}},
    )
    if not resultado.matched_count:
        raise HTTPException(status_code=404, detail="CART_ITEM_NOT_FOUND")
    return {"success": True}


def eliminar_item_carrito(db: Any, user: dict, item_id: str) -> dict:
    coleccion_carrito(db).delete_one(
        {"_id": str(item_id), "userId": str(user["_id"])}
    )
    return {"success": True}


def vaciar_carrito(db: Any, user: dict) -> dict:
    coleccion_carrito(db).delete_many({"userId": str(user["_id"])})
    return {"success": True}
