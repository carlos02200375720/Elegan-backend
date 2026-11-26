import logging
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import DESCENDING

from backend.configuracion import settings
from backend.conexión.mongodb import create_mongodb_client, get_database
from backend.rutas.anuncios import router_admin_anuncios, router_movil_anuncios
from backend.rutas.carrito import router_movil_carrito
from backend.rutas.autenticacion import router_admin, router_movil
from backend.rutas.cuenta import router_movil_cuenta
from backend.rutas.productos import router_admin_productos, router_movil_productos
from backend.rutas.categorias import router_admin_categorias, router_movil_categorias
from backend.rutas.productos_guardados import router_movil_productos_guardados
from backend.rutas.likes import router_movil_likes
from backend.rutas.compartidos import router_movil_compartidos
from backend.rutas.comentarios import router_movil_comentarios
from backend.rutas.moderacion import router_movil_moderacion, router_admin_moderacion
from backend.rutas.legal import router_movil_legal, router_admin_legal
from backend.rutas.ordenes import router_admin_ordenes, router_movil_ordenes
from backend.rutas.pagos_transferencia import router_movil_transferencia, router_admin_cuentas, router_admin_revision_transferencia
from backend.rutas.pagos_contraentrega import router_movil_contraentrega, router_admin_contraentrega
from backend.rutas.pagos_checkout import router_movil_checkout
from backend.rutas.cupones import router_admin_cupones, router_movil_cupones
from backend.rutas.usuario import router_admin_usuario, router_movil_usuario
from backend.rutas.mensajes import router_admin_mensajes, router_movil_mensajes, router_admin_mensajes_ws
from backend.rutas.eventos import router_eventos
from backend.rutas.media import router_admin_media, router_movil_media
from backend.logica.carrito import inicializar_indices_carrito
from backend.logica.productos import inicializar_indices_productos
from backend.logica.categorias import inicializar_indices_categorias
from backend.logica.productos_guardados import inicializar_indices_guardadas
from backend.logica.likes import inicializar_indices_likes
from backend.logica.compartidos import inicializar_indices_compartidos
from backend.logica.comentarios import inicializar_indices_comentarios
from backend.logica.moderacion import inicializar_indices_moderacion
from backend.logica.ordenes import inicializar_indices_ordenes
from backend.logica.cupones import inicializar_indices_cupones
from backend.logica.pagos_transferencia import inicializar_indices_cuentas_bancarias
from backend.logica.pagos_contraentrega import inicializar_configuracion_contraentrega
from backend.logica.mensajes import inicializar_indices_mensajes
from backend.logica.autenticacion import inicializar_super_admin

logger = logging.getLogger("elegan")


def _sanitizar_evento_sentry(event, hint):
    """Evita enviar datos personales o credenciales de las solicitudes a Sentry."""
    event.pop("user", None)
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value
                for key, value in headers.items()
                if key.lower() not in {"authorization", "cookie", "set-cookie"}
            }
        url = request.get("url")
        if isinstance(url, str):
            parsed = urlsplit(url)
            request["url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return event


if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        send_default_pii=False,
        traces_sample_rate=0.1,
        before_send=_sanitizar_evento_sentry,
    )


@asynccontextmanager
async def lifespan(application: FastAPI):
    if not settings.mongodb_uri:
        raise RuntimeError(
            "MONGODB_URI no está configurada. Se cancela el arranque del servicio."
        )

    mongo_client = create_mongodb_client()
    if mongo_client is None:
        raise RuntimeError(
            "No se pudo crear el cliente MongoDB. Se cancela el arranque del servicio."
        )

    try:
        database = get_database(mongo_client)
        mongo_client.admin.command("ping")

        inicializar_super_admin(database)

        anuncios = database["announcements"]
        anuncios.create_index("isActive")
        anuncios.create_index([("createdAt", DESCENDING)])
        inicializar_indices_productos(database)
        inicializar_indices_categorias(database)
        inicializar_indices_guardadas(database)
        inicializar_indices_likes(database)
        inicializar_indices_compartidos(database)
        inicializar_indices_comentarios(database)
        inicializar_indices_moderacion(database)
        inicializar_indices_carrito(database)
        inicializar_indices_ordenes(database)
        inicializar_indices_cupones(database)
        inicializar_indices_cuentas_bancarias(database)
        inicializar_configuracion_contraentrega(database)
        inicializar_indices_mensajes(database)

        application.state.mongodb_client = mongo_client
        application.state.mongodb = database
        logger.info("MongoDB conectado y todos los índices inicializados.")
    except Exception as exc:
        mongo_client.close()
        logger.exception(
            "No se pudo conectar a MongoDB o inicializar sus índices. "
            "Se cancela el arranque para impedir un despliegue sin base de datos."
        )
        raise RuntimeError(
            "MongoDB no está disponible o la inicialización de índices falló."
        ) from exc

    try:
        yield
    finally:
        mongo_client.close()


app = FastAPI(
    title="Elegan API",
    version="1.6.0",
    description="Backend central de Elegan.",
    lifespan=lifespan,
)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(router_movil)
app.include_router(router_movil_cuenta)
app.include_router(router_admin)
app.include_router(router_movil_productos)
app.include_router(router_admin_productos)
app.include_router(router_movil_categorias)
app.include_router(router_admin_categorias)
app.include_router(router_movil_anuncios)
app.include_router(router_admin_anuncios)
app.include_router(router_movil_productos_guardados)
app.include_router(router_movil_likes)
app.include_router(router_movil_compartidos)
app.include_router(router_movil_comentarios)
app.include_router(router_movil_moderacion)
app.include_router(router_admin_moderacion)
app.include_router(router_movil_legal)
app.include_router(router_admin_legal)
app.include_router(router_movil_carrito)
app.include_router(router_movil_transferencia)
app.include_router(router_movil_contraentrega)
app.include_router(router_movil_checkout)
app.include_router(router_admin_cuentas)
app.include_router(router_admin_revision_transferencia)
app.include_router(router_admin_contraentrega)
app.include_router(router_admin_cupones)
app.include_router(router_movil_cupones)
app.include_router(router_movil_ordenes)
app.include_router(router_admin_ordenes)
app.include_router(router_movil_usuario)
app.include_router(router_admin_usuario)
app.include_router(router_movil_mensajes)
app.include_router(router_admin_mensajes)
app.include_router(router_admin_mensajes_ws)
app.include_router(router_eventos)
app.include_router(router_movil_media)
app.include_router(router_admin_media)


@app.get("/", tags=["Sistema"])
def root():
    return {"service": "elegan-backend", "status": "running"}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
