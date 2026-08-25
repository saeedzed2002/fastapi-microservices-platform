from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "reference-service"
    service_version: str = "0.1.0"
    environment: str = "local"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="PLATFORM_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
