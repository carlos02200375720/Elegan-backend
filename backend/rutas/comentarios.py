from fastapi import APIRouter, Depends

from backend.modelo.comentarios import ComentarioCrear
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.comentarios import crear_comentario, listar_comentarios


router_movil_comentarios = APIRouter(
    prefix="/api/movil/comments", tags=["Comentarios móvil"]
)


@router_movil_comentarios.get("/{product_id}")
def obtener_comentarios(
    product_id: str,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return listar_comentarios(db, product_id)


@router_movil_comentarios.post("/{product_id}", status_code=201)
def publicar_comentario(
    product_id: str,
    datos: ComentarioCrear,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return crear_comentario(db, user, product_id, datos.text)
