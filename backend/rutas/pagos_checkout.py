from fastapi import APIRouter, Depends

from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.checkout import crear_orden_pago

router_movil_checkout = APIRouter(prefix="/api/movil/payments", tags=["Creación de pedidos"])


@router_movil_checkout.post("/orders", status_code=201)
def crear_orden(datos: dict, user=Depends(usuario_actual), db=Depends(obtener_db)):
    return crear_orden_pago(db, user, datos)
