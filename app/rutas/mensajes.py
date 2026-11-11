from fastapi import APIRouter, Depends

from app.esquemas.mensajes import MensajeCrear
from app.rutas.autenticacion import obtener_db, usuario_actual
from app.servicios.mensajes import crear_mensaje, listar_mensajes

router_movil_mensajes = APIRouter(
    prefix="/api/movil/messages", tags=["Mensajes móvil"]
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
