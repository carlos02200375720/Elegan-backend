from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def formatear_moneda(valor: Any) -> str:
    """Muestra únicamente importes enteros con punto como separador de millares."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return "0"
    if not numero.is_finite():
        return "0"
    entero = int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{entero:,}".replace(",", ".")
