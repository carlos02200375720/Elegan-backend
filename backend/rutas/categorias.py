from fastapi import APIRouter, Depends

from backend.modelo.categorias import CategoriaActualizar, CategoriaCrear
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db
from backend.logica.categorias import (
    actualizar_categoria,
    crear_categoria,
    eliminar_categoria,
    listar_categorias,
)

router_movil_categorias = APIRouter(
    prefix="/api/movil/categories", tags=["Categorías móvil"]
)
router_admin_categorias = APIRouter(
    prefix="/api/admin/categories",
    tags=["Categorías administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_categorias.get("")
def listar_categorias_movil(db=Depends(obtener_db)):
    return listar_categorias(db, solo_publicadas=True)


@router_admin_categorias.get("")
def listar_categorias_admin(db=Depends(obtener_db)):
    return listar_categorias(db)


@router_admin_categorias.post("", status_code=201)
def crear_categoria_admin(datos: CategoriaCrear, db=Depends(obtener_db)):
    return crear_categoria(db, datos.model_dump())


@router_admin_categorias.patch("/{categoria_id}")
def actualizar_categoria_admin(
    categoria_id: str, datos: CategoriaActualizar, db=Depends(obtener_db)
):
    return actualizar_categoria(
        db, categoria_id, datos.model_dump(exclude_unset=True)
    )


@router_admin_categorias.delete("/{categoria_id}")
def eliminar_categoria_admin(categoria_id: str, db=Depends(obtener_db)):
    return eliminar_categoria(db, categoria_id)
