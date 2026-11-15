from fastapi import APIRouter, Depends

from backend.modelo.ordenes import OrdenCrear
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.paypal import capturar_pago_paypal, crear_pago_paypal

router_movil_pagos = APIRouter(
    prefix="/api/movil/payments/paypal",
    tags=["Pagos PayPal"],
)


@router_movil_pagos.post("/orders", status_code=201)
def crear_orden_pago(
    datos: OrdenCrear,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return crear_pago_paypal(db, user, datos.model_dump())


@router_movil_pagos.post("/orders/{paypal_order_id}/capture")
def capturar_orden_pago(
    paypal_order_id: str,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return capturar_pago_paypal(db, user, paypal_order_id)
