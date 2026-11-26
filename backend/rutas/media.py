from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from backend.middleware.autorizacion import requerir_administrador
from backend.rutas.autenticacion import obtener_db, usuario_actual
from backend.logica.tareas_multimedia import procesar_tareas_multimedia
from backend.logica.media import guardar_multimedia


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
    background_tasks: BackgroundTasks,
    archivo: UploadFile = File(..., alias="file"),
    nombre: str | None = Form(default=None, alias="name"),
    _user=Depends(_verificar_admin_movil),
    db=Depends(obtener_db),
):
    resultado = guardar_multimedia(archivo, nombre, "movil", db=db)
    if resultado.get("processingTaskId"):
        background_tasks.add_task(procesar_tareas_multimedia, db)
    return resultado


@router_admin_media.post("", status_code=201)
def subir_multimedia_admin(
    background_tasks: BackgroundTasks,
    archivo: UploadFile = File(..., alias="file"),
    nombre: str | None = Form(default=None, alias="name"),
    db=Depends(obtener_db),
):
    resultado = guardar_multimedia(archivo, nombre, "admin", db=db)
    if resultado.get("processingTaskId"):
        background_tasks.add_task(procesar_tareas_multimedia, db)
    return resultado


@router_movil_media.post("/support", status_code=201)
def subir_adjunto_soporte(
    background_tasks: BackgroundTasks,
    archivo: UploadFile = File(..., alias="file"),
    nombre: str | None = Form(default=None, alias="name"),
    _user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    """Permite a cualquier cliente autenticado adjuntar fotos/videos al chat de soporte."""
    resultado = guardar_multimedia(archivo, nombre, "soporte", db=db)
    if resultado.get("processingTaskId"):
        background_tasks.add_task(procesar_tareas_multimedia, db)
    return resultado
