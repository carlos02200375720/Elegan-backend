import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.logica.autenticacion import verificar_token, validar_acceso_admin

logger = logging.getLogger("elegan.realtime")
router_eventos = APIRouter()

# Solo se emiten metadatos. Cada cliente vuelve a consultar su endpoint HTTP
# autorizado; el documento MongoDB completo nunca sale por el WebSocket.
COLECCIONES_EVENTOS = {
    "products", "store_categories", "announcements", "legal_documents",
    "orders", "cart", "supportMessages", "comments", "likes", "guardadas",
    "publication_shares", "coupons", "bank_accounts", "cash_on_delivery",
    "blocked_users", "comment_reports", "usuarios", "super-admins",
}
COLECCIONES_PUBLICAS_MOVIL = {
    "products", "store_categories", "announcements", "legal_documents",
    "coupons", "bank_accounts", "cash_on_delivery", "comments", "likes",
    "guardadas", "publication_shares",
}


class _RealtimeHub:
    """Un único Change Stream por instancia de backend, compartido por sus sockets."""

    def __init__(self):
        self._db = None
        self._task = None
        self._clients: dict[WebSocket, tuple[str, str]] = {}

    async def start(self, db):
        self._db = db
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._watch_changes())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._db = None

    def register(self, websocket: WebSocket, cliente: str, user_id: str):
        self._clients[websocket] = (cliente, user_id)

    def unregister(self, websocket: WebSocket):
        self._clients.pop(websocket, None)

    async def _watch_changes(self):
        pipeline = [{
            "$match": {
                "ns.coll": {"$in": sorted(COLECCIONES_EVENTOS)},
                "operationType": {"$in": ["insert", "update", "replace", "delete"]},
            }
        }]
        while True:
            cursor = None
            try:
                cursor = await asyncio.to_thread(
                    lambda: self._db.watch(
                        pipeline,
                        full_document="updateLookup",
                        max_await_time_ms=1000,
                    )
                )
                # Si MongoDB interrumpió el Change Stream y este se reabrió,
                # los clientes deben consultar de nuevo su estado para recuperar
                # cualquier cambio que haya ocurrido durante la interrupción.
                for websocket in list(self._clients):
                    try:
                        await websocket.send_json({"type": "connected"})
                    except Exception:
                        self.unregister(websocket)
                last_heartbeat = asyncio.get_running_loop().time()
                while True:
                    event = await asyncio.to_thread(cursor.try_next)
                    if event:
                        collection = str((event.get("ns") or {}).get("coll") or "")
                        document = event.get("fullDocument") or {}
                        owner_id = str(document.get("userId") or "")
                        document_id = str((event.get("documentKey") or {}).get("_id") or "")

                        payload = {
                            "type": "data_changed",
                            "collection": collection,
                            "operation": event.get("operationType"),
                            "documentId": document_id,
                        }
                        for websocket, (cliente, user_id) in list(self._clients.items()):
                            if cliente == "movil" and collection not in COLECCIONES_PUBLICAS_MOVIL:
                                # En deletes no existe fullDocument; se omiten los eventos
                                # privados sin propietario para no filtrar actividad ajena.
                                belongs_to_user = (
                                    bool(user_id)
                                    and (
                                        owner_id == user_id
                                        or (collection == "usuarios" and document_id == user_id)
                                    )
                                )
                                if not belongs_to_user:
                                    continue
                            try:
                                await websocket.send_json(payload)
                            except Exception:
                                self.unregister(websocket)

                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat >= 20:
                        for websocket in list(self._clients):
                            try:
                                await websocket.send_json({"type": "heartbeat"})
                            except Exception:
                                self.unregister(websocket)
                        last_heartbeat = now
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("El Change Stream general se interrumpió; se reintentará.")
                await asyncio.sleep(3)
            finally:
                if cursor is not None:
                    try:
                        await asyncio.to_thread(cursor.close)
                    except Exception:
                        pass


_hub = _RealtimeHub()


async def iniciar_observador_eventos(db):
    await _hub.start(db)


async def detener_observador_eventos():
    await _hub.stop()


async def _servir_eventos(websocket: WebSocket, cliente: str):
    await websocket.accept()
    try:
        # Evita mantener sockets abiertos indefinidamente sin completar autenticación.
        credenciales = await asyncio.wait_for(websocket.receive_json(), timeout=10)
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

        user_id = ""
        if token:
            try:
                usuario = verificar_token(token, db, cliente)
                if cliente == "admin":
                    validar_acceso_admin(usuario)
                user_id = str(usuario.get("_id") or "")
            except Exception:
                await websocket.close(code=4401, reason="INVALID_SESSION")
                return

        _hub.register(websocket, cliente, user_id)
        # Confirma que la sesión fue validada; el cliente usa esta señal para
        # resincronizar datos y recuperar eventos perdidos durante desconexiones.
        await websocket.send_json({"type": "connected"})
        # El Change Stream compartido envía eventos a esta conexión.
        while True:
            await websocket.receive_text()
    except asyncio.TimeoutError:
        try:
            await websocket.close(code=4408, reason="AUTH_TIMEOUT")
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Se cerró un socket del canal general (%s).", cliente)
        try:
            await websocket.close(code=1011, reason="EVENT_STREAM_ERROR")
        except Exception:
            pass
    finally:
        _hub.unregister(websocket)


@router_eventos.websocket("/api/admin/events/ws")
async def eventos_administracion(websocket: WebSocket):
    await _servir_eventos(websocket, "admin")


@router_eventos.websocket("/api/movil/events/ws")
async def eventos_movil(websocket: WebSocket):
    await _servir_eventos(websocket, "movil")
