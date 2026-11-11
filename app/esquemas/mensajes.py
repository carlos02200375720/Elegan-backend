from pydantic import BaseModel, ConfigDict


class MensajeCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
