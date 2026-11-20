from fastapi import APIRouter, Depends

from backend.modelo.ordenes import OrdenActualizarEstado
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.pagos import liberar_transferencias_vencidas
from backend.logica.ordenes import (
    actualizar_estado_orden,
    listar_ordenes,
)

router_movil_ordenes = APIRouter(
    prefix="/api/movil/orders", tags=["Órdenes móvil"]
)
router_admin_ordenes = APIRouter(
    prefix="/api/admin/orders",
    tags=["Órdenes administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_ordenes.get("")
def listar_ordenes_movil(
    user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return listar_ordenes(db, user, solo_usuario=True)


@router_admin_ordenes.get("")
def listar_ordenes_admin(
    user=Depends(requerir_administrador), db=Depends(obtener_db)
):
    liberar_transferencias_vencidas(db)
    return listar_ordenes(db, user, solo_usuario=False)


@router_admin_ordenes.patch("/{order_id}")
def actualizar_estado_orden_admin(
    order_id: str,
    datos: OrdenActualizarEstado,
    db=Depends(obtener_db),
):
    return actualizar_estado_orden(db, order_id, datos.status)
