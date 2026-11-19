import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from backend.configuracion import settings

DOP_POR_USD = Decimal("60.00")
CENTAVO_USD = Decimal("0.01")
EXPIRACION_PAGO_HORAS = 3


def _base_url() -> str:
    if settings.paypal_mode.strip().lower() != "sandbox":
        raise HTTPException(
            status_code=503,
            detail="PAYPAL_LIVE_DISABLED_SANDBOX_ONLY",
        )
    return "https://api-m.sandbox.paypal.com"


def _solicitud_paypal(
    metodo: str,
    ruta: str,
    token: str | None = None,
    cuerpo: dict | None = None,
    request_id: str | None = None,
) -> dict:
    url = _base_url() + ruta
    headers = {"Accept": "application/json", "Content-Type": "application/json", "Prefer": "return=representation"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    data = json.dumps(cuerpo or {}).encode("utf-8") if cuerpo is not None else None
    request = Request(url, data=data, headers=headers, method=metodo)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        detalle = error.read().decode("utf-8", errors="replace")
        # No se devuelve al cliente el cuerpo completo de PayPal ni datos internos.
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PAYPAL_API_ERROR",
                "paypalStatus": error.code,
            },
        ) from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="PAYPAL_UNAVAILABLE") from error


def obtener_token_paypal() -> str:
    client_id = settings.paypal_client_id.strip()
    client_secret = settings.paypal_client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="PAYPAL_NOT_CONFIGURED")

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        _base_url() + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise HTTPException(status_code=502, detail="PAYPAL_AUTH_FAILED") from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="PAYPAL_UNAVAILABLE") from error

    token = payload.get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="PAYPAL_AUTH_FAILED")
    return token


def convertir_dop_a_usd(total_dop: Decimal) -> Decimal:
    tasa = Decimal(str(settings.paypal_fixed_dop_per_usd))
    if tasa != DOP_POR_USD or tasa <= 0:
        raise HTTPException(status_code=503, detail="INVALID_FIXED_EXCHANGE_RATE")
    if total_dop <= 0:
        raise HTTPException(status_code=400, detail="INVALID_ORDER_TOTAL")
    total_usd = (total_dop / tasa).quantize(CENTAVO_USD, rounding=ROUND_HALF_UP)
    if total_usd <= 0:
        raise HTTPException(status_code=400, detail="ORDER_TOTAL_BELOW_PAYPAL_MINIMUM")
    return total_usd


def _decimal_precio(valor: Any) -> Decimal:
    try:
        precio = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="INVALID_PRODUCT_PRICE")
    if not precio.is_finite() or precio <= 0:
        raise HTTPException(status_code=409, detail="INVALID_PRODUCT_PRICE")
    return precio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_envio(valor: Any) -> Decimal:
    try:
        precio = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="INVALID_SHIPPING_PRICE")
    if not precio.is_finite() or precio < 0:
        raise HTTPException(status_code=409, detail="INVALID_SHIPPING_PRICE")
    return precio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _liberar_reservas_vencidas(db: Any) -> None:
    ahora = datetime.now(timezone.utc)
    ordenes = db["orders"].find({
        "paymentStatus": "pending",
        "inventoryReserved": True,
        "expiresAt": {"$lte": ahora},
    })
    for orden in ordenes:
        resultado = db["orders"].update_one(
            {"_id": orden["_id"], "paymentStatus": "pending", "inventoryReserved": True},
            {"$set": {"paymentStatus": "expired", "inventoryReserved": False}},
        )
        if resultado.modified_count:
            for item in orden.get("items", []):
                db["products"].update_one(
                    {"_id": item["productId"]},
                    {"$inc": {"stock": int(item["quantity"])}},
                )


def _reservar_inventario(db: Any, items: list[dict]) -> list[dict]:
    reservados = []
    for item in items:
        resultado = db["products"].update_one(
            {"_id": item["productId"], "stock": {"$gte": item["quantity"]}},
            {"$inc": {"stock": -item["quantity"]}},
        )
        if not resultado.modified_count:
            for reservado in reservados:
                db["products"].update_one(
                    {"_id": reservado["productId"]},
                    {"$inc": {"stock": reservado["quantity"]}},
                )
            raise HTTPException(status_code=409, detail="INSUFFICIENT_STOCK")
        reservados.append(item)
    return reservados


def _restaurar_inventario(db: Any, items: list[dict]) -> None:
    for item in items:
        db["products"].update_one(
            {"_id": item["productId"]},
            {"$inc": {"stock": item["quantity"]}},
        )


def crear_pago_paypal(db: Any, user: dict, datos: dict) -> dict:
    _liberar_reservas_vencidas(db)
    user_id = str(user["_id"])
    carrito = list(db["cart"].find({"userId": user_id}))
    if not carrito:
        raise HTTPException(status_code=400, detail="CART_EMPTY")

    items = []
    subtotal_dop = Decimal("0.00")
    shipping_total_dop = Decimal("0.00")
    total_dop = Decimal("0.00")
    for item in carrito:
        product_id = str(item.get("productId") or "")
        cantidad = item.get("quantity")
        if not product_id or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 1:
            raise HTTPException(status_code=409, detail="INVALID_CART_ITEM")
        producto = db["products"].find_one({"_id": product_id})
        if producto is None:
            raise HTTPException(status_code=409, detail="PRODUCT_NOT_FOUND")
        precio = _decimal_precio(producto.get("price"))
        stock = producto.get("stock")
        if isinstance(stock, bool) or not isinstance(stock, int):
            raise HTTPException(status_code=409, detail="PRODUCT_STOCK_NOT_CONFIGURED")
        if stock < cantidad:
            raise HTTPException(status_code=409, detail="INSUFFICIENT_STOCK")
        shipping_id = str(item.get("selectedShippingId") or "")
        shipping_methods = producto.get("shippingMethods") or []
        shipping_method = next(
            (method for method in shipping_methods if str(method.get("id") or "") == shipping_id),
            None,
        ) if shipping_id else None
        if shipping_methods and shipping_method is None:
            raise HTTPException(status_code=409, detail="SHIPPING_METHOD_REQUIRED")
        if shipping_id and shipping_method is None:
            raise HTTPException(status_code=409, detail="INVALID_SHIPPING_METHOD")
        shipping_price = _decimal_envio(shipping_method.get("price", 0)) if shipping_method else Decimal("0.00")
        subtotal_dop += precio * cantidad
        shipping_total_dop += shipping_price * cantidad
        total_dop += (precio + shipping_price) * cantidad
        items.append({
            "productId": product_id,
            "name": str(producto.get("name") or "Producto")[:200],
            "priceDOP": format(precio, ".2f"),
            "shippingMethodId": shipping_method.get("id", "") if shipping_method else "",
            "shippingMethodName": shipping_method.get("name", "") if shipping_method else "",
            "shippingPriceDOP": format(shipping_price, ".2f"),
            "shippingDeliveryTime": shipping_method.get("deliveryTime", "") if shipping_method else "",
            "shippingOrigin": shipping_method.get("origin", "") if shipping_method else "",
            "quantity": cantidad,
            "selectedSize": item.get("selectedSize"),
            "selectedColor": item.get("selectedColor"),
        })

    subtotal_dop = subtotal_dop.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    shipping_total_dop = shipping_total_dop.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_dop = total_dop.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_usd = convertir_dop_a_usd(total_dop)
    datos_limpios = dict(datos)
    for campo in (
        "_id", "userId", "role", "createdAt", "updatedAt", "total",
        "totalDOP", "totalUSD", "status", "paymentStatus", "paypalOrderId",
        "items", "itemCount", "itemsSummary", "exchangeRate",
    ):
        datos_limpios.pop(campo, None)
    nombre = str(datos_limpios.get("customerName") or user.get("name") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="INVALID_ORDER")

    ahora = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())
    expiracion = ahora + timedelta(hours=EXPIRACION_PAGO_HORAS)
    _reservar_inventario(db, items)
    orden = {
        **datos_limpios,
        "customerName": nombre,
        "_id": order_id,
        "userId": user_id,
        "items": items,
        "itemCount": sum(item["quantity"] for item in items),
        "itemsSummary": ", ".join(f"{item['name']} x{item['quantity']}" for item in items),
        "subtotalDOP": format(subtotal_dop, ".2f"),
        "shippingTotalDOP": format(shipping_total_dop, ".2f"),
        "total": format(total_dop, ".2f"),
        "totalDOP": format(total_dop, ".2f"),
        "totalUSD": format(total_usd, ".2f"),
        "exchangeRate": "60.00",
        "currency": "DOP",
        "paypalCurrency": "USD",
        "status": "pendiente_pago",
        "paymentStatus": "pending",
        "inventoryReserved": True,
        "createdAt": ahora,
        "expiresAt": expiracion,
    }
    try:
        db["orders"].insert_one(orden)
        token = obtener_token_paypal()
        respuesta = _solicitud_paypal(
            "POST",
            "/v2/checkout/orders",
            token=token,
            request_id=order_id,
            cuerpo={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": order_id,
                    "custom_id": order_id,
                    "invoice_id": order_id,
                    "description": "Compra en Elegan",
                    "amount": {
                        "currency_code": "USD",
                        "value": format(total_usd, ".2f"),
                    },
                }],
            },
        )
        paypal_id = respuesta.get("id")
        if not paypal_id:
            raise HTTPException(status_code=502, detail="PAYPAL_ORDER_CREATION_FAILED")
        db["orders"].update_one(
            {"_id": order_id},
            {"$set": {"paypalOrderId": paypal_id, "paypalStatus": respuesta.get("status", "CREATED")}},
        )
        approval_url = next(
            (link.get("href") for link in respuesta.get("links", []) if link.get("rel") in ("approve", "payer-action")),
            None,
        )
        return {
            "id": order_id,
            "paypalOrderId": paypal_id,
            "approvalUrl": approval_url,
            "amountDOP": format(total_dop, ".2f"),
            "amountUSD": format(total_usd, ".2f"),
            "currency": "USD",
            "exchangeRate": "60.00",
        }
    except Exception:
        db["orders"].delete_one({"_id": order_id, "paymentStatus": "pending"})
        _restaurar_inventario(db, items)
        raise


def capturar_pago_paypal(db: Any, user: dict, paypal_order_id: str) -> dict:
    user_id = str(user["_id"])
    orden = db["orders"].find_one({
        "paypalOrderId": paypal_order_id,
        "userId": user_id,
    })
    if orden is None:
        raise HTTPException(status_code=404, detail="PAYMENT_ORDER_NOT_FOUND")
    if orden.get("paymentStatus") == "completed":
        return {"id": str(orden["_id"]), "status": "paid", "paymentStatus": "completed"}
    if orden.get("paymentStatus") != "pending":
        raise HTTPException(status_code=409, detail="PAYMENT_NOT_PENDING")
    if orden.get("expiresAt") and orden["expiresAt"] <= datetime.now(timezone.utc):
        _liberar_reservas_vencidas(db)
        raise HTTPException(status_code=409, detail="PAYMENT_EXPIRED")

    token = obtener_token_paypal()
    respuesta = _solicitud_paypal(
        "POST",
        f"/v2/checkout/orders/{paypal_order_id}/capture",
        token=token,
        request_id=f"{orden['_id']}-capture",
        cuerpo={},
    )
    if respuesta.get("status") != "COMPLETED":
        raise HTTPException(status_code=402, detail="PAYMENT_NOT_COMPLETED")

    purchase_units = respuesta.get("purchase_units") or []
    if not purchase_units:
        raise HTTPException(status_code=502, detail="PAYPAL_CAPTURE_INVALID")
    unidad = purchase_units[0]
    if unidad.get("custom_id") != str(orden["_id"]):
        raise HTTPException(status_code=502, detail="PAYPAL_ORDER_REFERENCE_MISMATCH")
    capturas = (unidad.get("payments") or {}).get("captures") or []
    captura = next((c for c in capturas if c.get("status") == "COMPLETED"), None)
    if captura is None:
        raise HTTPException(status_code=402, detail="PAYMENT_NOT_COMPLETED")
    importe = captura.get("amount") or {}
    if importe.get("currency_code") != "USD" or importe.get("value") != orden.get("totalUSD"):
        raise HTTPException(status_code=502, detail="PAYPAL_AMOUNT_MISMATCH")

    ahora = datetime.now(timezone.utc)
    resultado = db["orders"].update_one(
        {"_id": orden["_id"], "userId": user_id, "paymentStatus": "pending"},
        {"$set": {
            "status": "confirmado",
            "paymentStatus": "completed",
            "paypalStatus": "COMPLETED",
            "paypalCaptureId": captura.get("id"),
            "paidAt": ahora,
            "inventoryReserved": False,
            "updatedAt": ahora,
        }},
    )
    if not resultado.modified_count:
        actual = db["orders"].find_one({"_id": orden["_id"], "userId": user_id})
        if actual and actual.get("paymentStatus") == "completed":
            return {"id": str(orden["_id"]), "status": "paid", "paymentStatus": "completed"}
        raise HTTPException(status_code=409, detail="PAYMENT_STATE_CHANGED")

    db["cart"].delete_many({"userId": user_id})
    return {
        "id": str(orden["_id"]),
        "status": "paid",
        "paymentStatus": "completed",
        "amountDOP": orden["totalDOP"],
        "amountUSD": orden["totalUSD"],
        "paypalCaptureId": captura.get("id"),
    }
