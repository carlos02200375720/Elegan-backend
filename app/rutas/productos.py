from fastapi import APIRouter, Depends

from app.esquemas.productos import ProductoActualizar, ProductoCrear
from app.middleware.autorizacion import requerir_administrador
from app.rutas.autenticacion import obtener_db
from app.servicios.productos import (
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
    return listar_productos(db)


@router_movil_productos.get("/{product_id}")
def obtener_producto_movil(product_id: str, db=Depends(obtener_db)):
    return obtener_producto(db, product_id)


@router_admin_productos.get("")
def listar_productos_admin(db=Depends(obtener_db)):
    return listar_productos(db)


@router_admin_productos.get("/{product_id}")
def obtener_producto_admin(product_id: str, db=Depends(obtener_db)):
    return obtener_producto(db, product_id)


@router_admin_productos.post("", status_code=201)
def crear_producto_admin(datos: ProductoCrear, db=Depends(obtener_db)):
    # Incluye los valores predeterminados definidos por el esquema del producto.
    return crear_producto(db, datos.model_dump())


@router_admin_productos.patch("/{product_id}")
def actualizar_producto_admin(
    product_id: str, datos: ProductoActualizar, db=Depends(obtener_db)
):
    return actualizar_producto(db, product_id, datos.model_dump(exclude_unset=True))


@router_admin_productos.delete("/{product_id}")
def eliminar_producto_admin(product_id: str, db=Depends(obtener_db)):
    return eliminar_producto(db, product_id)
