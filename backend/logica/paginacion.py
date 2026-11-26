"""Cursor pagination helpers shared by MongoDB list operations."""
import base64
import json
from datetime import datetime, timezone

from fastapi import HTTPException

TAMANO_PAGINA_PREDETERMINADO = 50
TAMANO_PAGINA_MAXIMO = 100


def decodificar_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"===")
        data = json.loads(raw.decode("utf-8"))
        fecha = datetime.fromisoformat(data["createdAt"])
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        identificador = str(data["id"])
        if not identificador:
            raise ValueError("empty id")
        return fecha, identificador
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(status_code=400, detail="INVALID_PAGE_CURSOR")


def codificar_cursor(documento: dict, campo_fecha: str = "createdAt") -> str:
    fecha = documento.get(campo_fecha)
    if not isinstance(fecha, datetime):
        fecha = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elif fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    payload = json.dumps({
        "createdAt": fecha.isoformat(),
        "id": str(documento.get("_id", "")),
    }, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def obtener_pagina(
    coleccion,
    filtro: dict | None = None,
    limit: int = TAMANO_PAGINA_PREDETERMINADO,
    cursor: str | None = None,
    direccion: int = -1,
) -> dict:
    """Paginación por rango (createdAt, _id), sin skip ni carga completa."""
    limite = min(TAMANO_PAGINA_MAXIMO, max(1, int(limit)))
    consulta = dict(filtro or {})
    posicion = decodificar_cursor(cursor)
    if posicion:
        fecha, identificador = posicion
        operador = "$gt" if direccion == 1 else "$lt"
        condicion = {"$or": [
            {"createdAt": {operador: fecha}},
            {"createdAt": fecha, "_id": {operador: identificador}},
        ]}
        consulta = {"$and": [consulta, condicion]} if consulta else condicion

    filas = list(
        coleccion.find(consulta)
        .sort([("createdAt", direccion), ("_id", direccion)])
        .limit(limite + 1)
    )
    hay_mas = len(filas) > limite
    items = filas[:limite]
    return {
        "documents": items,
        "hasMore": hay_mas,
        "nextCursor": codificar_cursor(items[-1]) if hay_mas and items else None,
    }
