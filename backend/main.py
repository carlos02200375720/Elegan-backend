import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import DESCENDING

from backend.configuracion import settings
from backend.conexión.mongodb import create_mongodb_client, get_database
from backend.rutas.anuncios import router_admin_anuncios, router_movil_anuncios
from backend.rutas.carrito import router_movil_carrito
from backend.rutas.autenticacion import router_admin, router_movil
from backend.rutas.productos import router_admin_productos, router_movil_productos
from backend.rutas.productos_guardados import router_movil_productos_guardados
from backend.rutas.ordenes import router_admin_ordenes, router_movil_ordenes
from backend.rutas.perfil import router_admin_perfil, router_movil_perfil
from backend.rutas.mensajes import router_admin_mensajes, router_movil_mensajes
from backend.rutas.media import router_admin_media, router_movil_media
from backend.logica.carrito import inicializar_indices_carrito
from backend.logica.productos_guardados import inicializar_indices_guardadas
from backend.logica.ordenes import inicializar_indices_ordenes
from backend.logica.perfil import inicializar_indices_perfiles
from backend.logica.mensajes import inicializar_indices_mensajes

logger = logging.getLogger("elegan")


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

        anuncios = database["announcements"]
        anuncios.create_index("isActive")
        anuncios.create_index([("createdAt", DESCENDING)])
        inicializar_indices_guardadas(database)
        inicializar_indices_carrito(database)
        inicializar_indices_ordenes(database)
        inicializar_indices_perfiles(database)
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
    version="1.5.0",
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
app.include_router(router_admin)
app.include_router(router_movil_productos)
app.include_router(router_admin_productos)
app.include_router(router_movil_anuncios)
app.include_router(router_admin_anuncios)
app.include_router(router_movil_productos_guardados)
app.include_router(router_movil_carrito)
app.include_router(router_movil_ordenes)
app.include_router(router_admin_ordenes)
app.include_router(router_movil_perfil)
app.include_router(router_admin_perfil)
app.include_router(router_movil_mensajes)
app.include_router(router_admin_mensajes)
app.include_router(router_movil_media)
app.include_router(router_admin_media)


@app.get("/", tags=["Sistema"])
def root():
    return {"service": "elegan-backend", "status": "running"}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
