from fastapi import APIRouter, Depends

from app.esquemas.anuncios import AnuncioActualizar, AnuncioCrear
from app.middleware.autorizacion import requerir_administrador
from app.rutas.autenticacion import obtener_db
from app.servicios.anuncios import (
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
def listar_anuncios_movil(db=Depends(obtener_db)):
    return listar_anuncios(db)


@router_admin_anuncios.get("")
def listar_anuncios_admin(db=Depends(obtener_db)):
    return listar_anuncios(db)


@router_admin_anuncios.post("", status_code=201)
def crear_anuncio_admin(datos: AnuncioCrear, db=Depends(obtener_db)):
    return crear_anuncio(db, datos.model_dump())


@router_admin_anuncios.patch("/{anuncio_id}")
def actualizar_anuncio_admin(
    anuncio_id: str, datos: AnuncioActualizar, db=Depends(obtener_db)
):
    return actualizar_anuncio(
        db, anuncio_id, datos.model_dump(exclude_unset=True)
    )


@router_admin_anuncios.delete("/{anuncio_id}")
def eliminar_anuncio_admin(anuncio_id: str, db=Depends(obtener_db)):
    return eliminar_anuncio(db, anuncio_id)
