from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    cors_origins: list[str] = []
    mongodb_uri: str = ""
    mongodb_database: str = "elegan"
    gcs_bucket_name: str = "elegan-bucket"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
