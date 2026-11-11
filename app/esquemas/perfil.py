from pydantic import BaseModel, ConfigDict


class PerfilActualizar(BaseModel):
    model_config = ConfigDict(extra="allow")
