from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "customer-service"
    service_version: str = "0.2.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://customer_service:customer-local-only@localhost:5432/customer_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.identity.events.v1"
    kafka_consumer_enabled: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="CUSTOMER_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
