from typing import Any


def validar_importe_entero(valor: Any, *, permitir_cero: bool = True) -> int:
    """Acepta exclusivamente enteros reales; nunca convierte ni redondea."""
    if type(valor) is not int or valor < 0 or (not permitir_cero and valor == 0):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="INVALID_AMOUNT")
    return valor


def formatear_moneda(valor: Any) -> str:
    """Formatea importes enteros con punto como separador de millares."""
    if type(valor) is not int or valor < 0:
        return "0"
    return f"{valor:,}".replace(",", ".")
