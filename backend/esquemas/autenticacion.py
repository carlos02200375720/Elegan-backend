from pydantic import BaseModel, EmailStr, Field, field_validator


class RegistroEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def limpiar_nombre(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INVALID_NAME")
        return value


class InicioSesionEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleEntrada(BaseModel):
    idToken: str = Field(min_length=1)
