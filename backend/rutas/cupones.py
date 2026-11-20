from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from backend.logica.cupones import (
    actualizar_cupon,
    crear_cupon,
    eliminar_cupon,
    listar_cupones,
    validar_cupon_cliente,
)
from backend.middleware.autorizacion import requerir_administrador
from backend.modelo.cupones import CuponActualizar, CuponCrear
from backend.rutas.autenticacion import obtener_db, usuario_actual

router_admin_cupones = APIRouter(
    prefix="/api/admin/coupons",
    tags=["Cupones administración"],
    dependencies=[Depends(requerir_administrador)],
)
router_movil_cupones = APIRouter(
    prefix="/api/movil/coupons",
    tags=["Cupones móvil"],
)


class CuponValidar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=40)
    subtotalDOP: Decimal = Field(gt=0)


@router_admin_cupones.get("")
def listar_cupones_admin(db=Depends(obtener_db)):
    return listar_cupones(db)


@router_admin_cupones.post("", status_code=201)
def crear_cupon_admin(datos: CuponCrear, db=Depends(obtener_db)):
    return crear_cupon(db, datos.model_dump())


@router_admin_cupones.patch("/{codigo}")
def actualizar_cupon_admin(
    codigo: str, datos: CuponActualizar, db=Depends(obtener_db)
):
    return actualizar_cupon(db, codigo, datos.model_dump(exclude_unset=True))


@router_admin_cupones.delete("/{codigo}")
def eliminar_cupon_admin(codigo: str, db=Depends(obtener_db)):
    return eliminar_cupon(db, codigo)


@router_movil_cupones.post("/validate")
def validar_cupon_movil(
    datos: CuponValidar,
    _user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return validar_cupon_cliente(db, datos.code, datos.subtotalDOP)
