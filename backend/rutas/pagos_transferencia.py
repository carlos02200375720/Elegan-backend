from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from google.api_core.exceptions import NotFound
from google.cloud import storage

from backend.configuracion import settings
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.modelo.pagos_transferencia import (
    CuentaBancariaCrear, CuentaBancariaActualizar, RevisionPagoTransferencia,
)
from backend.logica.pagos_transferencia import (
    adjuntar_comprobante, actualizar_cuenta_bancaria, crear_cuenta_bancaria,
    eliminar_cuenta_bancaria, listar_cuentas_bancarias, revisar_pago_transferencia,
)
from backend.logica.media import guardar_comprobante_privado

router_movil_transferencia = APIRouter(prefix="/api/movil/payments", tags=["Transferencia bancaria"])
router_admin_cuentas = APIRouter(prefix="/api/admin/bank-accounts", tags=["Cuentas bancarias"], dependencies=[Depends(requerir_administrador)])
router_admin_revision_transferencia = APIRouter(prefix="/api/admin/orders", tags=["Revisión de transferencia"], dependencies=[Depends(requerir_administrador)])


@router_movil_transferencia.get("/bank-accounts")
def cuentas_activas(db=Depends(obtener_db), _user=Depends(usuario_actual)):
    return listar_cuentas_bancarias(db, solo_activas=True)


@router_movil_transferencia.post("/orders/{order_id}/proof", status_code=201)
def subir_comprobante(order_id: str, archivo: UploadFile = File(..., alias="file"), user=Depends(usuario_actual), db=Depends(obtener_db)):
    order = db["orders"].find_one({"_id": order_id, "userId": str(user["_id"])})
    if order is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    expires_at = order.get("expiresAt")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="PROOF_EXPIRED")
    if order.get("paymentMethod") != "bank_transfer" or order.get("paymentStatus") not in ("awaiting_proof", "proof_rejected"):
        raise HTTPException(status_code=409, detail="PROOF_NOT_ALLOWED")
    if archivo.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="PROOF_IMAGE_ONLY")
    if archivo.size is not None and archivo.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PROOF_TOO_LARGE")
    saved = guardar_comprobante_privado(archivo, f"comprobante-{order_id}")
    return adjuntar_comprobante(db, user, order_id, saved["objectName"])


@router_admin_cuentas.get("")
def listar_cuentas(db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return listar_cuentas_bancarias(db)


@router_admin_cuentas.post("", status_code=201)
def crear_cuenta(datos: CuentaBancariaCrear, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return crear_cuenta_bancaria(db, datos.model_dump())


@router_admin_cuentas.patch("/{account_id}")
def actualizar_cuenta(account_id: str, datos: CuentaBancariaActualizar, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return actualizar_cuenta_bancaria(db, account_id, datos.model_dump(exclude_unset=True))


@router_admin_cuentas.delete("/{account_id}")
def eliminar_cuenta(account_id: str, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return eliminar_cuenta_bancaria(db, account_id)


@router_admin_revision_transferencia.patch("/{order_id}/payment-review")
def revisar_pago(order_id: str, datos: RevisionPagoTransferencia, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return revisar_pago_transferencia(db, order_id, datos.approved, datos.note)


@router_admin_revision_transferencia.get("/{order_id}/proof")
def ver_comprobante(order_id: str, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    order = db["orders"].find_one({"_id": order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    object_name = str(order.get("paymentProofObjectName") or "")
    if not object_name or not settings.gcs_private_bucket_name:
        raise HTTPException(status_code=404, detail="PROOF_NOT_FOUND")
    blob = storage.Client().bucket(settings.gcs_private_bucket_name).blob(object_name)
    try:
        if not blob.exists():
            raise HTTPException(status_code=404, detail="PROOF_NOT_FOUND")
        blob.reload()
        def stream_object():
            with blob.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        return StreamingResponse(stream_object(), media_type=blob.content_type or "application/octet-stream", headers={"Cache-Control": "private, no-store"})
    except NotFound as error:
        raise HTTPException(status_code=404, detail="PROOF_NOT_FOUND") from error
