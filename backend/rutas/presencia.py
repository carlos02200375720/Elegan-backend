from fastapi import APIRouter, Depends

from backend.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from backend.logica.presencia import (
    obtener_usuarios_activos,
    registrar_actividad,
)

router_movil_presencia = APIRouter(
    prefix="/api/movil/presence",
    tags=["Presencia móvil"],
)
router_admin_presencia = APIRouter(
    prefix="/api/admin/presence",
    tags=["Presencia administración"],
)


@router_movil_presencia.post("/heartbeat")
def heartbeat_movil(
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return registrar_actividad(db, user)


@router_admin_presencia.get("/active-users")
def usuarios_activos_admin(
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return obtener_usuarios_activos(db)
