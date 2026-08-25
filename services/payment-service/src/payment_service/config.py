from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "payment-service"
    service_version: str = "0.5.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://payment_service:payment-local-only@localhost:5432/payment_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_reservation_topic: str = "fastapi-platform.inventory.events.v1"
    kafka_topic: str = "fastapi-platform.payment.events.v1"
    kafka_publisher_enabled: bool = False
    kafka_consumer_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)

    model_config = SettingsConfigDict(env_prefix="PAYMENT_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
