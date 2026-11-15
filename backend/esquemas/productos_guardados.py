from pydantic import BaseModel, ConfigDict


class ProductoGuardadoActualizar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    saved: bool | None = None
