from pydantic import BaseModel, ConfigDict, Field


class CuentaBancariaCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bankName: str = Field(min_length=1, max_length=100)
    accountNumber: str = Field(min_length=1, max_length=80)
    accountType: str = Field(min_length=1, max_length=50)
    holderName: str = Field(min_length=1, max_length=150)
    holderDocument: str = Field(default="", max_length=40)
    isActive: bool = True


class CuentaBancariaActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bankName: str | None = Field(default=None, min_length=1, max_length=100)
    accountNumber: str | None = Field(default=None, min_length=1, max_length=80)
    accountType: str | None = Field(default=None, min_length=1, max_length=50)
    holderName: str | None = Field(default=None, min_length=1, max_length=150)
    holderDocument: str | None = Field(default=None, max_length=40)
    isActive: bool | None = None


class RevisionPagoTransferencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    note: str = ""
