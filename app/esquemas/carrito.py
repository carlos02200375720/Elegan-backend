from pydantic import BaseModel, ConfigDict, Field


class CarritoAgregar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    productId: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1, le=99)
    selectedSize: str | None = None
    selectedColor: str | None = None


class CarritoActualizar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity: int = Field(ge=1, le=99)
