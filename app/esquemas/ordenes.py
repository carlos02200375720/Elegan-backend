from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrdenCrear(BaseModel):
    model_config = ConfigDict(extra="allow")

    customerName: str = Field(min_length=1, max_length=200)

    @field_validator("customerName")
    @classmethod
    def limpiar_nombre_cliente(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("INVALID_ORDER")
        return value
