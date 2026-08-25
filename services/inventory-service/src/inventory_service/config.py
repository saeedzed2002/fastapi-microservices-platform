from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "inventory-service"
    service_version: str = "0.5.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://inventory_service:inventory-local-only@localhost:5432/"
        "inventory_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    log_level: str = "INFO"
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.inventory.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_publisher_enabled: bool = False
    kafka_consumer_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)

    model_config = SettingsConfigDict(env_prefix="INVENTORY_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
