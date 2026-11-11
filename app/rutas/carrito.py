from fastapi import APIRouter, Depends

from app.esquemas.carrito import CarritoActualizar, CarritoAgregar
from app.rutas.autenticacion import obtener_db, usuario_actual
from app.servicios.carrito import (
    actualizar_item_carrito,
    agregar_al_carrito,
    eliminar_item_carrito,
    obtener_carrito,
    vaciar_carrito,
)

router_movil_carrito = APIRouter(
    prefix="/api/movil/cart", tags=["Carrito móvil"]
)


@router_movil_carrito.get("")
def listar_carrito(user=Depends(usuario_actual), db=Depends(obtener_db)):
    return obtener_carrito(db, user)


@router_movil_carrito.post("", status_code=201)
def agregar_item(
    datos: CarritoAgregar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return agregar_al_carrito(db, user, datos.model_dump())


@router_movil_carrito.patch("/{item_id}")
def actualizar_item(
    item_id: str,
    datos: CarritoActualizar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return actualizar_item_carrito(db, user, item_id, datos.quantity)


@router_movil_carrito.delete("/{item_id}")
def eliminar_item(
    item_id: str, user=Depends(usuario_actual), db=Depends(obtener_db)
):
    return eliminar_item_carrito(db, user, item_id)


@router_movil_carrito.delete("")
def vaciar_carrito_usuario(user=Depends(usuario_actual), db=Depends(obtener_db)):
    return vaciar_carrito(db, user)
