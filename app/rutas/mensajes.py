from fastapi import APIRouter, Depends, Query

from app.esquemas.mensajes import MensajeCrear, RespuestaAdminCrear
from app.middleware.autorizacion import requerir_administrador
from app.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from app.servicios.mensajes import (
    crear_mensaje,
    listar_mensajes,
    listar_mensajes_admin,
    responder_mensaje_admin,
)

router_movil_mensajes = APIRouter(
    prefix="/api/movil/messages", tags=["Mensajes móvil"]
)
router_admin_mensajes = APIRouter(
    prefix="/api/admin/messages",
    tags=["Mensajes administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_mensajes.get("")
def obtener_mensajes(
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return listar_mensajes(db, user)


@router_movil_mensajes.post("", status_code=201)
def enviar_mensaje(
    datos: MensajeCrear,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return crear_mensaje(db, user, datos.model_dump())


@router_admin_mensajes.get("")
def obtener_mensajes_admin(
    user_id: str | None = Query(default=None, min_length=1),
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return listar_mensajes_admin(db, user_id)


@router_admin_mensajes.post("/{user_id}", status_code=201)
def responder_cliente_admin(
    user_id: str,
    datos: RespuestaAdminCrear,
    admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return responder_mensaje_admin(db, user_id, admin, datos.model_dump())
