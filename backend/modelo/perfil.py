from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PerfilActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def limpiar_nombre(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("INVALID_NAME")
        return value

    @field_validator("phone", "address", "city")
    @classmethod
    def limpiar_texto(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
