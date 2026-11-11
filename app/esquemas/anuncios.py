from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnuncioCrear(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    imageUrl: str = ""
    tag: str = ""
    discount: Any = ""
    isActive: bool = True

    @field_validator("title")
    @classmethod
    def limpiar_titulo(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INVALID_ANNOUNCEMENT")
        return value


class AnuncioActualizar(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    imageUrl: str | None = None
    tag: str | None = None
    discount: Any = None
    isActive: bool | None = None

    @field_validator("title")
    @classmethod
    def limpiar_titulo(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("INVALID_ANNOUNCEMENT")
        return value
