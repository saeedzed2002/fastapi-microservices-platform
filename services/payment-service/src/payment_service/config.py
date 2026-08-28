from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "payment-service"
    service_version: str = "0.6.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://payment_service:payment-local-only@localhost:5432/payment_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    order_base_url: str = "http://localhost:8004"
    order_request_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_reservation_topic: str = "fastapi-platform.inventory.events.v1"
    kafka_topic: str = "fastapi-platform.payment.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_publisher_enabled: bool = False
    kafka_consumer_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    zarinpal_merchant_id: str = ""
    zarinpal_sandbox: bool = True
    zarinpal_callback_url: str = "https://localhost/api/v1/payments/zarinpal/callback"
    zarinpal_request_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    zarinpal_currency: str = "IRT"
    reservation_minutes: int = Field(default=15, ge=1, le=1440)
    expiry_worker_enabled: bool = False
    expiry_poll_interval_seconds: float = Field(default=5.0, ge=0.1, le=60.0)

    model_config = SettingsConfigDict(env_prefix="PAYMENT_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
