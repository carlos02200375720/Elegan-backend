from pydantic import BaseModel, ConfigDict, StrictBool


class LikeActualizar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    liked: StrictBool
