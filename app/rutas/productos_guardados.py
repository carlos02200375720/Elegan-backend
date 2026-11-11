from fastapi import APIRouter, Body, Depends

from app.esquemas.productos_guardados import ProductoGuardadoActualizar
from app.rutas.autenticacion import obtener_db, usuario_actual
from app.servicios.productos_guardados import (
    cambiar_producto_guardado,
    listar_productos_guardados,
)

router_movil_productos_guardados = APIRouter(
    prefix="/api/movil/saved", tags=["Productos guardados móvil"]
)


@router_movil_productos_guardados.get("")
def listar_guardados(
    user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return listar_productos_guardados(db, user)


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
