from typing import Any
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _importe_entero(value):
    try:
        numero = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("INVALID_AMOUNT")
    if not numero.is_finite() or numero < 0:
        raise ValueError("INVALID_AMOUNT")
    return int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class MetodoEnvioProducto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    price: int = Field(ge=0)
    deliveryTime: str = Field(min_length=1, max_length=100)

    @field_validator("price", mode="before")
    @classmethod
    def precio_entero(cls, value):
        return _importe_entero(value)
    origin: str = Field(min_length=1, max_length=120)


class ProductoBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "todo"
    price: int = Field(default=0, ge=0)
    imageUrl: str = ""
    images: list[str] = Field(default_factory=list)
    videoUrl: str = ""
    videoPoster: str = ""
    hasVideo: bool = False
    mediaFormat: str = "1:1"
    sizes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    shippingMethods: list[MetodoEnvioProducto] = Field(default_factory=list, max_length=12)
    stock: int = Field(default=10, ge=0)
    isActive: bool = False
    allowCashOnDelivery: bool = True
    isFeatured: bool = True
    reviewCount: int = Field(default=0, ge=0)
    rating: float = Field(default=5.0, ge=0, le=5)

    @field_validator("price", mode="before")
    @classmethod
    def precio_entero(cls, value):
        return _importe_entero(value)

    @field_validator("name")
    @classmethod
    def limpiar_nombre(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INVALID_PRODUCT")
        return value

    @field_validator("category")
    @classmethod
    def limpiar_categoria(cls, value: str) -> str:
        return value.strip().lower() or "todo"


class ProductoCrear(ProductoBase):
    id: str | None = None


class ProductoActualizar(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = None
    price: int | None = Field(default=None, ge=0)
    imageUrl: str | None = None
    images: list[str] | None = None
    videoUrl: str | None = None
    videoPoster: str | None = None
    hasVideo: bool | None = None
    mediaFormat: str | None = None
    sizes: list[str] | None = None
    colors: list[str] | None = None
    shippingMethods: list[MetodoEnvioProducto] | None = Field(default=None, max_length=12)
    stock: int | None = Field(default=None, ge=0)
    isActive: bool | None = None
    allowCashOnDelivery: bool | None = None
    isFeatured: bool | None = None
    reviewCount: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)

    @field_validator("price", mode="before")
    @classmethod
    def precio_entero(cls, value):
        return None if value is None else _importe_entero(value)

    @field_validator("category")
    @classmethod
    def limpiar_categoria(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower() or "todo"
