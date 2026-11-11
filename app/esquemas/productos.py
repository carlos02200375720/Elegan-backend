from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductoBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "todo"
    price: float = Field(default=0, ge=0)
    imageUrl: str = ""
    images: list[str] = Field(default_factory=list)
    videoUrl: str = ""
    videoPoster: str = ""
    hasVideo: bool = False
    mediaFormat: str = "1:1"
    sizes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    stock: int = Field(default=10, ge=0)
    isFeatured: bool = True
    reviewCount: int = Field(default=0, ge=0)
    rating: float = Field(default=5.0, ge=0, le=5)

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
    price: float | None = Field(default=None, ge=0)
    imageUrl: str | None = None
    images: list[str] | None = None
    videoUrl: str | None = None
    videoPoster: str | None = None
    hasVideo: bool | None = None
    mediaFormat: str | None = None
    sizes: list[str] | None = None
    colors: list[str] | None = None
    stock: int | None = Field(default=None, ge=0)
    isFeatured: bool | None = None
    reviewCount: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
