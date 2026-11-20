from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from google.api_core.exceptions import NotFound
from google.cloud import storage

from backend.configuracion import settings


def eliminar_cuenta_cliente(db: Any, user: dict) -> dict:
    """Elimina la cuenta y sus datos personales asociados.

    Los pedidos se conservan únicamente como registros comerciales anonimizados;
    se eliminan sus datos de contacto, vínculo con el cliente y comprobantes.
    """
    if user.get("role") != "customer":
        raise HTTPException(status_code=403, detail="CUSTOMER_ACCOUNT_REQUIRED")

    user_id = str(user.get("_id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="INVALID_SESSION")

    usuarios = db["usuarios"]
    if usuarios.find_one({"_id": user_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    ordenes = list(db["orders"].find(
        {"userId": user_id},
        {"_id": 1, "paymentProofObjectName": 1},
    ))

    # Primero se eliminan los comprobantes privados. Si GCS falla, se conserva
    # la cuenta para que el usuario pueda reintentar sin perder acceso.
    object_names = {
        str(order.get("paymentProofObjectName") or "").strip()
        for order in ordenes
    }
    object_names.discard("")
    if object_names:
        if not settings.gcs_private_bucket_name:
            raise HTTPException(
                status_code=503, detail="PRIVATE_PROOF_STORAGE_NOT_CONFIGURED"
            )
        try:
            bucket = storage.Client().bucket(settings.gcs_private_bucket_name)
            for object_name in object_names:
                if not object_name.startswith("comprobantes/"):
                    raise HTTPException(
                        status_code=409, detail="INVALID_PROOF_OBJECT"
                    )
                try:
                    bucket.blob(object_name).delete()
                except NotFound:
                    # Un reintento después de una eliminación parcial es seguro.
                    continue
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=502, detail="ACCOUNT_PROOF_CLEANUP_FAILED"
            ) from error

    ahora = datetime.now(timezone.utc)

    # Se conservan datos de la transacción necesarios para auditoría comercial,
    # pero se elimina toda referencia identificable al cliente.
    for order in ordenes:
        db["orders"].update_one(
            {"_id": order["_id"], "userId": user_id},
            {
                "$unset": {
                    "userId": "",
                    "customerName": "",
                    "email": "",
                    "phone": "",
                    "address": "",
                    "city": "",
                    "paymentProofObjectName": "",
                    "paymentProofUrl": "",
                    "proofSubmittedAt": "",
                },
                "$set": {
                    "customerDataAnonymized": True,
                    "customerDataAnonymizedAt": ahora,
                    "updatedAt": ahora,
                },
            },
        )

    # Datos personales y actividad que no necesitan conservarse.
    colecciones_usuario = (
        "cart",
        "guardadas",
        "likes",
        "publication_shares",
        "comments",
        "supportMessages",
    )
    for collection_name in colecciones_usuario:
        db[collection_name].delete_many({"userId": user_id})

    # El documento de usuario contiene el perfil, correo y hash de contraseña.
    resultado = usuarios.delete_one({"_id": user_id})
    if resultado.deleted_count != 1:
        raise HTTPException(status_code=409, detail="ACCOUNT_DELETION_INCOMPLETE")

    return {
        "success": True,
        "deleted": True,
        "anonymizedOrders": len(ordenes),
    }
