from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException


def normalizar_importe_entero(valor: Any, *, permitir_cero: bool = True) -> int:
    """Convierte cualquier importe recibido a entero antes de guardarlo o calcularlo."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="INVALID_AMOUNT")
    if not numero.is_finite():
        raise HTTPException(status_code=400, detail="INVALID_AMOUNT")
    entero = int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if entero < 0 or (not permitir_cero and entero == 0):
        raise HTTPException(status_code=400, detail="INVALID_AMOUNT")
    return entero


def formatear_moneda(valor: Any) -> str:
    """Muestra importes enteros con punto como separador de millares."""
    try:
        entero = normalizar_importe_entero(valor)
    except HTTPException:
        return "0"
    return f"{entero:,}".replace(",", ".")
