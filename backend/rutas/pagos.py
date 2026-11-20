from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.pagos import (
    adjuntar_comprobante, actualizar_cuenta_bancaria, crear_cuenta_bancaria,
    crear_orden_pago, eliminar_cuenta_bancaria, listar_cuentas_bancarias,
    revisar_pago_transferencia,
)
from backend.logica.media import guardar_multimedia

router_movil_pagos = APIRouter(prefix="/api/movil/payments", tags=["Pagos móviles"])
router_admin_cuentas = APIRouter(prefix="/api/admin/bank-accounts", tags=["Cuentas bancarias"],
    dependencies=[Depends(requerir_administrador)])
router_admin_pagos = APIRouter(prefix="/api/admin/orders", tags=["Revisión de pagos"],
    dependencies=[Depends(requerir_administrador)])


@router_movil_pagos.get("/bank-accounts")
def cuentas_activas(db=Depends(obtener_db), _user=Depends(usuario_actual)):
    return listar_cuentas_bancarias(db, solo_activas=True)


@router_movil_pagos.post("/orders", status_code=201)
def crear_orden(datos: dict, user=Depends(usuario_actual), db=Depends(obtener_db)):
    return crear_orden_pago(db, user, datos)


@router_movil_pagos.post("/orders/{order_id}/proof", status_code=201)
def subir_comprobante(order_id: str, archivo: UploadFile = File(..., alias="file"),
                      user=Depends(usuario_actual), db=Depends(obtener_db)):
    if archivo.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="PROOF_IMAGE_ONLY")
    if archivo.size is not None and archivo.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PROOF_TOO_LARGE")
    saved = guardar_multimedia(archivo, f"comprobante-{order_id}", "comprobantes")
    return adjuntar_comprobante(db, user, order_id, saved["url"])


@router_admin_cuentas.get("")
def listar_cuentas(db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return listar_cuentas_bancarias(db)


@router_admin_cuentas.post("", status_code=201)
def crear_cuenta(datos: dict, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return crear_cuenta_bancaria(db, datos)


@router_admin_cuentas.patch("/{account_id}")
def actualizar_cuenta(account_id: str, datos: dict, db=Depends(obtener_db),
                      _user=Depends(requerir_administrador)):
    return actualizar_cuenta_bancaria(db, account_id, datos)


@router_admin_cuentas.delete("/{account_id}")
def eliminar_cuenta(account_id: str, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return eliminar_cuenta_bancaria(db, account_id)


@router_admin_pagos.patch("/{order_id}/payment-review")
def revisar_pago(order_id: str, datos: dict, db=Depends(obtener_db),
                 _user=Depends(requerir_administrador)):
    approved = datos.get("approved")
    if not isinstance(approved, bool):
        raise HTTPException(status_code=400, detail="APPROVED_BOOLEAN_REQUIRED")
    return revisar_pago_transferencia(db, order_id, approved, datos.get("note", ""))
