from fastapi import APIRouter, Depends, Query

from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.compartidos import (
    obtener_conteos_compartidos,
    registrar_compartido,
)

router_movil_compartidos = APIRouter(
    prefix="/api/movil/shares", tags=["Compartidos móvil"]
)


@router_movil_compartidos.get("/counts")
def consultar_conteos_compartidos(
    product_ids: list[str] = Query(default=[], alias="productIds", max_length=100),
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return obtener_conteos_compartidos(db, product_ids)


@router_movil_compartidos.post("/{product_id}")
def crear_compartido(
    product_id: str,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return registrar_compartido(db, user, product_id)
