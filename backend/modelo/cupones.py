from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _importe_entero(value):
    try:
        numero = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("INVALID_COUPON_VALUE")
    if not numero.is_finite() or numero <= 0:
        raise ValueError("INVALID_COUPON_VALUE")
    return int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class CuponCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=40)
    discountType: Literal["percentage", "fixed"]
    discountValue: int = Field(gt=0)
    isActive: bool = True

    @field_validator("code")
    @classmethod
    def limpiar_codigo(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("INVALID_COUPON_CODE")
        return value

    @field_validator("discountValue", mode="before")
    @classmethod
    def validar_valor(cls, value, info):
        entero = _importe_entero(value)
        if info.data.get("discountType") == "percentage" and entero > 100:
            raise ValueError("INVALID_COUPON_VALUE")
        return entero


class CuponActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discountType: Literal["percentage", "fixed"] | None = None
    discountValue: int | None = Field(default=None, gt=0)
    isActive: bool | None = None

    @field_validator("discountValue", mode="before")
    @classmethod
    def validar_valor(cls, value):
        return _importe_entero(value) if value is not None else None
