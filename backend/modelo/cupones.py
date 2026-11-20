from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CuponCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=40)
    discountType: Literal["percentage", "fixed"]
    discountValue: float = Field(gt=0)
    isActive: bool = True

    @field_validator("code")
    @classmethod
    def limpiar_codigo(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("INVALID_COUPON_CODE")
        return value

    @field_validator("discountValue")
    @classmethod
    def validar_valor(cls, value: float, info):
        if info.data.get("discountType") == "percentage" and value > 100:
            raise ValueError("INVALID_COUPON_VALUE")
        return round(value, 2)


class CuponActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discountType: Literal["percentage", "fixed"] | None = None
    discountValue: float | None = Field(default=None, gt=0)
    isActive: bool | None = None

    @field_validator("discountValue")
    @classmethod
    def validar_valor(cls, value: float | None) -> float | None:
        if value is not None and value > 100000000:
            raise ValueError("INVALID_COUPON_VALUE")
        return round(value, 2) if value is not None else value
