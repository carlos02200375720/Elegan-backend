from fastapi import APIRouter, Depends

from backend.modelo.usuario import UsuarioActualizar
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from backend.logica.usuario import (
    actualizar_usuario,
    actualizar_usuario_admin,
    obtener_usuario,
    obtener_usuario_admin,
)

router_movil_usuario = APIRouter(
    prefix="/api/movil/profile", tags=["Usuario móvil"]
)
router_admin_usuario = APIRouter(
    prefix="/api/admin/profile",
    tags=["Usuario administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_usuario.get("")
def leer_usuario_movil(
    user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return obtener_usuario(db, user)


@router_movil_usuario.put("")
def guardar_usuario_movil(
    datos: UsuarioActualizar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return actualizar_usuario(
        db, user, datos.model_dump(exclude_unset=True, exclude_none=True)
    )


@router_admin_usuario.get("")
def leer_usuario_admin(
    user=Depends(usuario_actual_admin), db=Depends(obtener_db)
):
    return obtener_usuario_admin(db, user)


@router_admin_usuario.put("")
def guardar_usuario_admin(
    datos: UsuarioActualizar,
    user=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return actualizar_usuario_admin(
        db, user, datos.model_dump(exclude_unset=True, exclude_none=True)
    )
