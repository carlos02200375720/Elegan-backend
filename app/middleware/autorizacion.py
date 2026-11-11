from fastapi import Depends

from app.rutas.autenticacion import usuario_actual_admin
from app.servicios.autenticacion import validar_acceso_admin


def requerir_cliente(user=Depends(usuario_actual)):
    if user.get("role") not in ("customer", "admin", "superadmin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="ACCESS_DENIED")
    return user


def requerir_administrador(user=Depends(usuario_actual_admin)):
    validar_acceso_admin(user)
    return user
