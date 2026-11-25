from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def formatear_moneda(valor: Any) -> str:
    """Formato dominicano: 1.500 / 1.500,50; sin decimales si es entero."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return "0"
    if not numero.is_finite():
        return "0"
    numero = numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if texto.endswith(",00"):
        texto = texto[:-3]
    else:
        texto = texto.rstrip("0").rstrip(",")
    return texto
