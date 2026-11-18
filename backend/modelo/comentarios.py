from pydantic import BaseModel, ConfigDict, Field


class ComentarioCrear(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, max_length=1000, strict=True)
