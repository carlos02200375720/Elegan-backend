import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from backend.logica.autenticacion import verificar_token, validar_acceso_admin

logger = logging.getLogger("elegan.realtime")
router_eventos = APIRouter()

# Solo se emiten metadatos de cambios. Los clientes vuelven a consultar sus
# endpoints HTTP autorizados; nunca se transmite el documento MongoDB completo.
COLECCIONES_EVENTOS = {
    "products",
    "store_categories",
    "announcements",
    "legal_documents",
    "orders",
    "cart",
    "supportMessages",
    "comments",
    "likes",
    "guardadas",
    "publication_shares",
    "coupons",
    "bank_accounts",
    "bankAccounts",
    "cash_on_delivery",
    "cashOnDelivery",
    "blocked_users",
    "comment_reports",
    "reported_comments",
    "usuarios",
    "super-admins",
}

COLECCIONES_PUBLICAS_MOVIL = {
    "products",
    "store_categories",
    "announcements",
    "legal_documents",
    "coupons",
    "bank_accounts",
    "bankAccounts",
    "cash_on_delivery",
    "cashOnDelivery",
    "comments",
    "likes",
    "guardadas",
    "publication_shares",
}


async def _servir_eventos(websocket: WebSocket, cliente: str) -> None:
    await websocket.accept()
    cursor = None
    try:
        credenciales = await websocket.receive_json()
        token = (
            str(credenciales.get("token") or "").strip()
            if isinstance(credenciales, dict)
            else ""
        )
        if not token and cliente == "admin":
            await websocket.close(code=4401, reason="AUTH_REQUIRED")
            return

        db = getattr(websocket.app.state, "mongodb", None)
        if db is None:
            await websocket.close(code=1013, reason="DATABASE_NOT_CONFIGURED")
            return

        usuario = None
        if token:
            try:
                usuario = verificar_token(token, db, cliente)
                if cliente == "admin":
                    validar_acceso_admin(usuario)
            except Exception:
                await websocket.close(code=4401, reason="INVALID_SESSION")
                return

        pipeline = [{
            "$match": {
                "ns.coll": {"$in": sorted(COLECCIONES_EVENTOS)},
                "operationType": {"$in": ["insert", "update", "replace", "delete"]},
            }
        }]
        cursor = await asyncio.to_thread(
            lambda: db.watch(
                pipeline,
                full_document="updateLookup",
                max_await_time_ms=1000,
            )
        )
        ultimo_heartbeat = asyncio.get_running_loop().time()

        while True:
            evento = await asyncio.to_thread(cursor.try_next)
            if evento:
                coleccion = str((evento.get("ns") or {}).get("coll") or "")
                documento = evento.get("fullDocument") or {}
                user_id = str(documento.get("userId") or "")

                if cliente == "movil":
                    if coleccion not in COLECCIONES_PUBLICAS_MOVIL:
                        # Los cambios privados solo se notifican al dueño del dato.
                        # En eliminaciones MongoDB no incluye fullDocument; se omiten
                        # para no revelar actividad de otras cuentas.
                        pertenece_al_usuario = bool(usuario) and (
                            user_id == str(usuario.get("_id"))
                            or (coleccion == "usuarios" and str(documento.get("_id") or "") == str(usuario.get("_id")))
                        )
                        if not pertenece_al_usuario:
                            continue

                clave = evento.get("documentKey") or {}
                await websocket.send_json(jsonable_encoder({
                    "type": "data_changed",
                    "collection": coleccion,
                    "operation": evento.get("operationType"),
                    "documentId": str(clave.get("_id") or ""),
                }))

            ahora = asyncio.get_running_loop().time()
            if ahora - ultimo_heartbeat >= 20:
                await websocket.send_json({"type": "heartbeat"})
                ultimo_heartbeat = ahora

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Se cerró el flujo WebSocket general (%s).", cliente)
        try:
            await websocket.close(code=1011, reason="EVENT_STREAM_ERROR")
        except Exception:
            pass
    finally:
        if cursor is not None:
            try:
                await asyncio.to_thread(cursor.close)
            except Exception:
                pass


@router_eventos.websocket("/api/admin/events/ws")
async def eventos_administracion(websocket: WebSocket):
    await _servir_eventos(websocket, "admin")


@router_eventos.websocket("/api/movil/events/ws")
async def eventos_movil(websocket: WebSocket):
    await _servir_eventos(websocket, "movil")
