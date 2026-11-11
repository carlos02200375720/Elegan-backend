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
from app.servicios.carrito import inicializar_indices_carrito
from app.servicios.productos_guardados import inicializar_indices_guardadas
from app.servicios.ordenes import inicializar_indices_ordenes
from app.servicios.perfil import inicializar_indices_perfiles
from app.servicios.mensajes import inicializar_indices_mensajes


@asynccontextmanager
async def lifespan(application: FastAPI):
    mongo_client = create_mongodb_client()
    application.state.mongodb_client = mongo_client
    application.state.mongodb = (
        get_database(mongo_client) if mongo_client is not None else None
    )
    if application.state.mongodb is not None:
        anuncios = application.state.mongodb["announcements"]
        anuncios.create_index("isActive")
        anuncios.create_index([("createdAt", DESCENDING)])
        inicializar_indices_guardadas(application.state.mongodb)
        inicializar_indices_carrito(application.state.mongodb)
        inicializar_indices_ordenes(application.state.mongodb)
        inicializar_indices_perfiles(application.state.mongodb)
        inicializar_indices_mensajes(application.state.mongodb)
    try:
        yield
    finally:
        if mongo_client is not None:
            mongo_client.close()


app = FastAPI(
    title="Elegan API",
    version="1.4.0",
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


@app.get("/", tags=["Sistema"])
def root():
    return {"service": "elegan-backend", "status": "running"}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
