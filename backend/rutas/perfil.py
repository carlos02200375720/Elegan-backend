from fastapi import APIRouter, Depends

from backend.modelo.perfil import PerfilActualizar
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from backend.logica.perfil import (
    actualizar_perfil,
    actualizar_perfil_cliente,
    obtener_perfil,
    obtener_perfil_cliente,
)

router_movil_perfil = APIRouter(
    prefix="/api/movil/profile", tags=["Perfil móvil"]
)
router_admin_perfil = APIRouter(
    prefix="/api/admin/profile",
    tags=["Perfil administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_perfil.get("")
def leer_perfil_movil(
    user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return obtener_perfil_cliente(db, user)


@router_movil_perfil.put("")
def guardar_perfil_movil(
    datos: PerfilActualizar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return actualizar_perfil_cliente(
        db, user, datos.model_dump(exclude_unset=True, exclude_none=True)
    )


@router_admin_perfil.get("")
def leer_perfil_admin(
    user=Depends(usuario_actual_admin), db=Depends(obtener_db)
):
    return obtener_perfil(db, user)


@router_admin_perfil.put("")
def guardar_perfil_admin(
    datos: PerfilActualizar,
    user=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return actualizar_perfil(db, user, datos.model_dump(exclude_unset=True, exclude_none=True))
