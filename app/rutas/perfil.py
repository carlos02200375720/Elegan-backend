from fastapi import APIRouter, Depends

from app.esquemas.perfil import PerfilActualizar
from app.middleware.autorizacion import requerir_administrador
from app.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from app.servicios.perfil import actualizar_perfil, obtener_perfil

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
    return obtener_perfil(db, user)


@router_movil_perfil.put("")
def guardar_perfil_movil(
    datos: PerfilActualizar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return actualizar_perfil(db, user, datos.model_dump())


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
    return actualizar_perfil(db, user, datos.model_dump())
