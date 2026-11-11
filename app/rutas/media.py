from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.middleware.autorizacion import requerir_administrador
from app.rutas.autenticacion import usuario_actual
from app.servicios.media import guardar_multimedia


router_movil_media = APIRouter(
    prefix="/api/movil/media", tags=["Multimedia móvil"]
)
router_admin_media = APIRouter(
    prefix="/api/admin/media",
    tags=["Multimedia administración"],
    dependencies=[Depends(requerir_administrador)],
)


def _verificar_admin_movil(user=Depends(usuario_actual)):
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")
    return user


@router_movil_media.post("", status_code=201)
def subir_multimedia_movil(
    archivo: UploadFile = File(..., alias="file"),
    nombre: str | None = Form(default=None, alias="name"),
    _user=Depends(_verificar_admin_movil),
):
    return guardar_multimedia(archivo, nombre)


@router_admin_media.post("", status_code=201)
def subir_multimedia_admin(
    archivo: UploadFile = File(..., alias="file"),
    nombre: str | None = Form(default=None, alias="name"),
):
    return guardar_multimedia(archivo, nombre)
