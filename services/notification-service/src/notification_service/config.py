from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "notification-service"
    service_version: str = "0.6.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://notification_service:notification-local-only@localhost:5432/"
        "notification_service"
    )
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_invoice_topic: str = "fastapi-platform.order.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_consumer_enabled: bool = False
    rabbitmq_url: str = "amqp://platform:platform-local-only@localhost:5672//"
    task_dispatcher_enabled: bool = False
    task_dispatcher_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    email_processing_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from_email: str = "no-reply@fastapi-platform.local"
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
