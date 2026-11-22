from fastapi import APIRouter, Depends

from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db
from backend.modelo.pagos_contraentrega import ConfiguracionContraentrega
from backend.logica.pagos_contraentrega import (
    obtener_configuracion_contraentrega, actualizar_configuracion_contraentrega,
)

router_movil_contraentrega = APIRouter(prefix="/api/movil/payments", tags=["Pago contra entrega"])
router_admin_contraentrega = APIRouter(prefix="/api/admin/cash-on-delivery", tags=["Pago contra entrega"], dependencies=[Depends(requerir_administrador)])


@router_movil_contraentrega.get("/cash-on-delivery")
def obtener_contraentrega(db=Depends(obtener_db)):
    return obtener_configuracion_contraentrega(db)


@router_admin_contraentrega.get("")
def obtener_contraentrega_admin(db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return obtener_configuracion_contraentrega(db)


@router_admin_contraentrega.put("")
def guardar_contraentrega_admin(datos: ConfiguracionContraentrega, db=Depends(obtener_db), _user=Depends(requerir_administrador)):
    return actualizar_configuracion_contraentrega(db, datos.model_dump())
