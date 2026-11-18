from fastapi import APIRouter, Body, Depends, Query

from backend.modelo.productos_guardados import ProductoGuardadoActualizar
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.productos_guardados import (
    cambiar_producto_guardado,
    listar_productos_guardados,
    obtener_conteos_guardados,
)

router_movil_productos_guardados = APIRouter(
    prefix="/api/movil/saved", tags=["Productos guardados móvil"]
)


@router_movil_productos_guardados.get("")
def listar_guardados(
    user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return listar_productos_guardados(db, user)


@router_movil_productos_guardados.get("/counts")
def consultar_conteos_guardados(
    product_ids: list[str] = Query(default=[], alias="productIds", max_length=100),
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return obtener_conteos_guardados(db, product_ids)


@router_movil_productos_guardados.put("/{product_id}")
def actualizar_guardado(
    product_id: str,
    datos: ProductoGuardadoActualizar | None = Body(default=None),
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return cambiar_producto_guardado(
        db, user, product_id, datos.saved if datos is not None else None
    )
