from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoriaCrear(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    imageUrl: str = ""
    icon: str = "category"
    sortOrder: int = 0
    isActive: bool = False

    @field_validator("name")
    @classmethod
    def limpiar_nombre(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INVALID_CATEGORY")
        return value


class CategoriaActualizar(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    imageUrl: str | None = None
    icon: str | None = None
    sortOrder: int | None = None
    isActive: bool | None = None

    @field_validator("name")
    @classmethod
    def limpiar_nombre(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("INVALID_CATEGORY")
        return value
