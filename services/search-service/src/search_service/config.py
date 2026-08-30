from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "search-service"
    service_version: str = "0.8.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://search_service:search-local-only@localhost:5432/search_service"
    )
    redis_url: str = "redis://localhost:6379/2"
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_catalog_topic: str = "fastapi-platform.catalog.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_group: str = "search-service.catalog"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_consumer_enabled: bool = False
    public_rate_limit: int = Field(default=60, ge=1, le=10000)
    public_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="SEARCH_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
