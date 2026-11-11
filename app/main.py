import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import DESCENDING

from app.configuracion import settings
from app.infraestructura.mongodb import create_mongodb_client, get_database
from app.rutas.anuncios import router_admin_anuncios, router_movil_anuncios
from app.rutas.carrito import router_movil_carrito
from app.rutas.autenticacion import router_admin, router_movil
from app.rutas.productos import router_admin_productos, router_movil_productos
from app.rutas.productos_guardados import router_movil_productos_guardados
from app.rutas.ordenes import router_admin_ordenes, router_movil_ordenes
from app.rutas.perfil import router_admin_perfil, router_movil_perfil
from app.rutas.mensajes import router_admin_mensajes, router_movil_mensajes
from app.rutas.media import router_admin_media, router_movil_media
from app.servicios.carrito import inicializar_indices_carrito
from app.servicios.productos_guardados import inicializar_indices_guardadas
from app.servicios.ordenes import inicializar_indices_ordenes
from app.servicios.perfil import inicializar_indices_perfiles
from app.servicios.mensajes import inicializar_indices_mensajes

logger = logging.getLogger("elegan")


@asynccontextmanager
async def lifespan(application: FastAPI):
    mongo_client = None
    application.state.mongodb_client = None
    application.state.mongodb = None

    # Cloud Run debe poder iniciar HTTP aunque MongoDB tenga una interrupción
    # temporal. PyMongo reintenta la selección de servidor en las operaciones
    # posteriores; los errores quedan registrados para diagnóstico.
    try:
        mongo_client = create_mongodb_client()
        application.state.mongodb_client = mongo_client

        if mongo_client is not None:
            database = get_database(mongo_client)
            application.state.mongodb = database

            try:
                mongo_client.admin.command("ping")
                anuncios = database["announcements"]
                anuncios.create_index("isActive")
                anuncios.create_index([("createdAt", DESCENDING)])
                inicializar_indices_guardadas(database)
                inicializar_indices_carrito(database)
                inicializar_indices_ordenes(database)
                inicializar_indices_perfiles(database)
                inicializar_indices_mensajes(database)
                logger.info("MongoDB conectado e índices inicializados.")
            except Exception:
                logger.exception(
                    "MongoDB no está disponible o no se pudieron inicializar "
                    "los índices. FastAPI continuará arrancando; las operaciones "
                    "que necesiten MongoDB podrían fallar hasta recuperar la conexión."
                )
        else:
            logger.warning(
                "MONGODB_URI no está configurada. La API arrancará sin MongoDB."
            )
    except Exception:
        logger.exception(
            "No se pudo crear o configurar el cliente MongoDB. "
            "FastAPI continuará arrancando sin conexión a la base de datos."
        )
        application.state.mongodb_client = None
        application.state.mongodb = None

    try:
        yield
    finally:
        if mongo_client is not None:
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
