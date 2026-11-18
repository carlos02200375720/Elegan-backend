from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.rutas.autenticacion import obtener_db
from backend.logica.autenticacion import verificar_token
from backend.logica.compartidos import (
    obtener_conteos_compartidos,
    registrar_compartido,
)

router_movil_compartidos = APIRouter(
    prefix="/api/movil/shares", tags=["Compartidos móvil"]
)


class DatosCompartido(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visitor_id: str | None = Field(default=None, alias="visitorId", max_length=128)
    event_id: str | None = Field(default=None, alias="eventId", max_length=128)
    from_guest_session: bool = Field(default=False, alias="fromGuestSession")


@router_movil_compartidos.get("/counts")
def consultar_conteos_compartidos(
    product_ids: list[str] = Query(default=[], alias="productIds", max_length=100),
    db=Depends(obtener_db),
):
    return obtener_conteos_compartidos(db, product_ids)


@router_movil_compartidos.post("/{product_id}")
def crear_compartido(
    product_id: str,
    datos: DatosCompartido | None = None,
    authorization: str | None = Header(default=None),
    db=Depends(obtener_db),
):
    user = None
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="INVALID_AUTHORIZATION")
        token = authorization[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="INVALID_AUTHORIZATION")
        # Si se envía un token, debe ser válido; nunca se degrada a visitante.
        user = verificar_token(token, db, "movil")
    else:
        if datos is None or not datos.from_guest_session:
            raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
        if not datos.visitor_id:
            raise HTTPException(status_code=422, detail="VISITOR_ID_REQUIRED")

    return registrar_compartido(
        db,
        product_id,
        user=user,
        visitor_id=datos.visitor_id if datos else None,
        event_id=datos.event_id if datos else None,
    )
