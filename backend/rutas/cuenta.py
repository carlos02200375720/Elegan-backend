from fastapi import APIRouter, Depends

from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.eliminacion_cuenta import eliminar_cuenta_cliente

router_movil_cuenta = APIRouter(
    prefix="/api/movil/account",
    tags=["Cuenta móvil"],
)


@router_movil_cuenta.delete("")
def eliminar_cuenta_movil(
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return eliminar_cuenta_cliente(db, user)
