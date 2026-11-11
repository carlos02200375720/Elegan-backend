from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    cors_origins: str = ""
    mongodb_uri: str = ""
    mongodb_database: str = "elegan"
    gcs_bucket_name: str = "elegan-bucket"
    jwt_secret: str = ""
    google_web_client_id: str = ""
    super_admin_email: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
