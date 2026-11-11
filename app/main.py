from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.configuracion import settings
from app.infraestructura.mongodb import create_mongodb_client, get_database
from app.rutas.autenticacion import router_admin, router_movil
from app.rutas.productos import router_admin_productos, router_movil_productos


@asynccontextmanager
async def lifespan(application: FastAPI):
    mongo_client = create_mongodb_client()
    application.state.mongodb_client = mongo_client
    application.state.mongodb = (
        get_database(mongo_client) if mongo_client is not None else None
    )
    try:
        yield
    finally:
        if mongo_client is not None:
            mongo_client.close()


app = FastAPI(
    title="Elegan API",
    version="1.2.0",
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


@app.get("/", tags=["Sistema"])
def root():
    return {"service": "elegan-backend", "status": "running"}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
