from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from backend.modelo.mensajes import MensajeCrear, RespuestaAdminCrear
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import (
    obtener_db,
    usuario_actual,
    usuario_actual_admin,
)
from backend.logica.mensajes import (
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


# WebSocket separado del router HTTP para autenticar el token en el primer mensaje
# (el navegador no permite establecer el encabezado Authorization al abrir WebSocket).
import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect
from backend.logica.autenticacion import verificar_token
from backend.logica.mensajes import coleccion_mensajes, formatear_mensaje

logger = logging.getLogger("elegan.mensajes.websocket")
router_admin_mensajes_ws = APIRouter()


@router_admin_mensajes_ws.websocket("/api/admin/messages/ws")
async def transmitir_mensajes_admin(websocket: WebSocket):
    await websocket.accept()
    cursor = None
    try:
        credenciales = await websocket.receive_json()
        token = str(credenciales.get("token") or "").strip() if isinstance(credenciales, dict) else ""
        if not token:
            await websocket.close(code=4401, reason="AUTH_REQUIRED")
            return

        db = getattr(websocket.app.state, "mongodb", None)
        if db is None:
            await websocket.close(code=1013, reason="DATABASE_NOT_CONFIGURED")
            return

        try:
            admin = verificar_token(token, db, "admin")
        except Exception:
            await websocket.close(code=4401, reason="INVALID_ADMIN_SESSION")
            return

        from backend.logica.autenticacion import validar_acceso_admin
        validar_acceso_admin(admin)

        # Change Streams permite recibir inserciones aunque el POST y el WebSocket
        # lleguen a instancias distintas de Cloud Run.
        cursor = await asyncio.to_thread(
            lambda: coleccion_mensajes(db).watch(
                [{"$match": {"operationType": "insert"}}],
                full_document="default",
                max_await_time_ms=1000,
            )
        )
        ultimo_heartbeat = asyncio.get_running_loop().time()

        while True:
            evento = await asyncio.to_thread(cursor.try_next)
            if evento and evento.get("fullDocument"):
                mensaje = formatear_mensaje(dict(evento["fullDocument"]))
                await websocket.send_json(jsonable_encoder({
                    "type": "message_created",
                    "message": mensaje,
                }))

            ahora = asyncio.get_running_loop().time()
            if ahora - ultimo_heartbeat >= 20:
                await websocket.send_json({"type": "heartbeat"})
                ultimo_heartbeat = ahora

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Se cerró el flujo WebSocket de mensajes administrativos.")
        try:
            await websocket.close(code=1011, reason="MESSAGE_STREAM_ERROR")
        except Exception:
            pass
    finally:
        if cursor is not None:
            try:
                await asyncio.to_thread(cursor.close)
            except Exception:
                pass
