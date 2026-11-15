from pydantic import BaseModel, ConfigDict, StrictInt


class CarritoAgregar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    productId: str
    quantity: StrictInt = 1
    selectedSize: str | None = None
    selectedColor: str | None = None


class CarritoActualizar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity: StrictInt
