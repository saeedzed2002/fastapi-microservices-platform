from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "shipping-service"
    service_version: str = "0.1.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://shipping_service:shipping-local-only@localhost:5432/shipping_service"
    )
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_order_topic: str = "fastapi-platform.order.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_group: str = "shipping-service.order"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_consumer_enabled: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="SHIPPING_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
