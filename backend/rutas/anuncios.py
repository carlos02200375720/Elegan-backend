from fastapi import APIRouter, BackgroundTasks, Depends, Query

from backend.modelo.anuncios import AnuncioActualizar, AnuncioCrear
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db
from backend.logica.tareas_multimedia import procesar_tareas_multimedia
from backend.logica.anuncios import (
    actualizar_anuncio,
    crear_anuncio,
    eliminar_anuncio,
    listar_anuncios,
)

router_movil_anuncios = APIRouter(
    prefix="/api/movil/announcements", tags=["Anuncios móvil"]
)
router_admin_anuncios = APIRouter(
    prefix="/api/admin/announcements",
    tags=["Anuncios administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_anuncios.get("")
def listar_anuncios_movil(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    db=Depends(obtener_db),
):
    return listar_anuncios(db, limit, cursor)


@router_admin_anuncios.get("")
def listar_anuncios_admin(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    db=Depends(obtener_db),
):
    return listar_anuncios(db, limit, cursor)


@router_admin_anuncios.post("", status_code=201)
def crear_anuncio_admin(datos: AnuncioCrear, db=Depends(obtener_db)):
    return crear_anuncio(db, datos.model_dump())


@router_admin_anuncios.patch("/{anuncio_id}")
def actualizar_anuncio_admin(
    anuncio_id: str,
    datos: AnuncioActualizar,
    background_tasks: BackgroundTasks,
    db=Depends(obtener_db),
):
    resultado = actualizar_anuncio(
        db, anuncio_id, datos.model_dump(exclude_unset=True)
    )
    background_tasks.add_task(procesar_tareas_multimedia, db)
    return resultado


@router_admin_anuncios.delete("/{anuncio_id}")
def eliminar_anuncio_admin(
    anuncio_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(obtener_db),
):
    resultado = eliminar_anuncio(db, anuncio_id)
    background_tasks.add_task(procesar_tareas_multimedia, db)
    return resultado
