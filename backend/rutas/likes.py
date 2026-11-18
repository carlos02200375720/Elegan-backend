from fastapi import APIRouter, Depends, Query

from backend.modelo.likes import LikeActualizar
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.likes import (
    cambiar_like,
    listar_likes_usuario,
    obtener_conteos_likes,
)

router_movil_likes = APIRouter(
    prefix="/api/movil/likes", tags=["Likes móvil"]
)


@router_movil_likes.get("")
def listar_likes(user=Depends(usuario_actual), db=Depends(obtener_db)):
    return listar_likes_usuario(db, user)


@router_movil_likes.get("/counts")
def consultar_conteos_likes(
    product_ids: list[str] = Query(default=[], alias="productIds", max_length=100),
    db=Depends(obtener_db),
):
    return obtener_conteos_likes(db, product_ids)


@router_movil_likes.put("/{product_id}")
def actualizar_like(
    product_id: str,
    datos: LikeActualizar,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return cambiar_like(db, user, product_id, datos.liked)
