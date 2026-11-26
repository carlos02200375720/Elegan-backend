from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

COD_TERMS_VERSION = "2026-11-19"
CONFIG_COD = "cash_on_delivery"
CONFIG_COD_ID = "configuracion"
COD_DEFAULT_MESSAGE = "Paga tu pedido cuando lo recibas. Verifica los productos y confirma la recepción al momento de la entrega."


def preparar_pago_contraentrega(db: Any, data: dict, now: datetime, session: Any = None) -> dict:
    if not obtener_configuracion_contraentrega(db, session=session)["enabled"]:
        raise HTTPException(status_code=409, detail="COD_DISABLED")
    if (
        data.get("cashOnDeliveryAccepted") is not True
        or data.get("cashOnDeliveryTermsVersion") != COD_TERMS_VERSION
    ):
        raise HTTPException(status_code=400, detail="COD_TERMS_NOT_ACCEPTED")
    return {
        "paymentStatus": "cash_on_delivery", "status": "pendiente_confirmacion",
        "cashOnDeliveryAccepted": True, "cashOnDeliveryTermsVersion": COD_TERMS_VERSION,
        "cashOnDeliveryAcceptedAt": now, "expiresAt": None, "bankAccount": None,
    }


def validar_producto_para_contraentrega(product: dict) -> None:
    if product.get("allowCashOnDelivery", True) is not True:
        raise HTTPException(status_code=409, detail="COD_PRODUCT_NOT_ALLOWED")


def inicializar_configuracion_contraentrega(db: Any) -> None:
    now = datetime.now(timezone.utc)
    db[CONFIG_COD].update_one(
        {"_id": CONFIG_COD_ID},
        {"$setOnInsert": {"enabled": True, "message": COD_DEFAULT_MESSAGE,
                          "createdAt": now, "updatedAt": now}},
        upsert=True,
    )


def obtener_configuracion_contraentrega(db: Any, session: Any = None) -> dict:
    config = db[CONFIG_COD].find_one({"_id": CONFIG_COD_ID}, session=session) or {}
    return {
        "enabled": bool(config.get("enabled", True)),
        "message": str(config.get("message") or COD_DEFAULT_MESSAGE),
        "termsVersion": COD_TERMS_VERSION,
    }


def actualizar_configuracion_contraentrega(db: Any, data: dict) -> dict:
    enabled, message = data.get("enabled"), data.get("message")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="COD_ENABLED_BOOLEAN_REQUIRED")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="COD_MESSAGE_REQUIRED")
    now = datetime.now(timezone.utc)
    db[CONFIG_COD].update_one(
        {"_id": CONFIG_COD_ID},
        {"$set": {"enabled": enabled, "message": message.strip()[:3000], "updatedAt": now},
         "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    return obtener_configuracion_contraentrega(db)
