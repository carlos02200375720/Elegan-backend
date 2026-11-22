from pydantic import BaseModel, ConfigDict, Field


class ConfiguracionContraentrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    message: str = Field(min_length=1, max_length=3000)


class AceptacionContraentrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cashOnDeliveryAccepted: bool
    cashOnDeliveryTermsVersion: str = Field(min_length=1, max_length=40)
