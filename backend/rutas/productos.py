from fastapi import APIRouter, Depends

from backend.modelo.productos import ProductoActualizar, ProductoCrear
from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db
from backend.logica.productos import (
    actualizar_producto,
    crear_producto,
    eliminar_producto,
    listar_productos,
    obtener_producto,
)

router_movil_productos = APIRouter(
    prefix="/api/movil/products", tags=["Productos móvil"]
)
router_admin_productos = APIRouter(
    prefix="/api/admin/products",
    tags=["Productos administración"],
    dependencies=[Depends(requerir_administrador)],
)


@router_movil_productos.get("")
def listar_productos_movil(db=Depends(obtener_db)):
    # El catálogo móvil expone productos publicados y su conteo persistente de comentarios.
    return listar_productos(
        db,
        solo_publicados=True,
        incluir_conteo_comentarios=True,
    )


@router_movil_productos.get("/{product_id}")
def obtener_producto_movil(product_id: str, db=Depends(obtener_db)):
    # Un borrador no puede consultarse desde la API móvil.
    return obtener_producto(db, product_id, solo_publicados=True)


@router_admin_productos.get("")
def listar_productos_admin(db=Depends(obtener_db)):
    # El panel necesita ver tanto borradores como productos publicados.
    return listar_productos(db)


@router_admin_productos.get("/{product_id}")
def obtener_producto_admin(product_id: str, db=Depends(obtener_db)):
    return obtener_producto(db, product_id)


@router_admin_productos.post("", status_code=201)
def crear_producto_admin(datos: ProductoCrear, db=Depends(obtener_db)):
    # Los productos nuevos quedan como borrador salvo publicación explícita.
    return crear_producto(db, datos.model_dump())


@router_admin_productos.patch("/{product_id}")
def actualizar_producto_admin(
    product_id: str, datos: ProductoActualizar, db=Depends(obtener_db)
):
    return actualizar_producto(db, product_id, datos.model_dump(exclude_unset=True))


@router_admin_productos.delete("/{product_id}")
def eliminar_producto_admin(product_id: str, db=Depends(obtener_db)):
    return eliminar_producto(db, product_id)
