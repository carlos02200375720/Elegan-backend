from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.rutas.autenticacion import obtener_db, usuario_actual, usuario_actual_admin
from backend.logica.moderacion import (
    actualizar_reporte,
    bloquear_usuario,
    listar_reportes,
    reportar_comentario,
)

router_movil_moderacion = APIRouter(prefix="/api/movil", tags=["Moderación móvil"])
router_admin_moderacion = APIRouter(prefix="/api/admin/moderation", tags=["Moderación administrativa"])


class ReporteComentarioEntrada(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class EstadoReporteEntrada(BaseModel):
    status: str = Field(min_length=1, max_length=20)


@router_movil_moderacion.post("/comments/{comment_id}/report")
def crear_reporte(
    comment_id: str,
    datos: ReporteComentarioEntrada,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return reportar_comentario(db, user, comment_id, datos.reason)


@router_movil_moderacion.post("/users/{user_id}/block")
def bloquear(
    user_id: str,
    user=Depends(usuario_actual),
    db=Depends(obtener_db),
):
    return bloquear_usuario(db, user, user_id)


@router_admin_moderacion.get("/reports")
def obtener_reportes(
    status: str = "pending",
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return listar_reportes(db, status)


@router_admin_moderacion.patch("/reports/{report_id}")
def cambiar_estado_reporte(
    report_id: str,
    datos: EstadoReporteEntrada,
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return actualizar_reporte(db, report_id, datos.status)
