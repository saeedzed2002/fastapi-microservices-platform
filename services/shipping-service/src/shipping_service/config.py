from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_auth import reject_known_local_development_credentials


class Settings(BaseSettings):
    service_name: str = "shipping-service"
    service_version: str = "0.1.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://shipping_service:shipping-local-only@localhost:5432/shipping_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    order_base_url: str = "http://localhost:8007"
    order_internal_access_secret: str = Field(
        default="local-development-order-shipping-access-secret-change-me-32-bytes",
        min_length=32,
    )
    order_internal_access_previous_secret: str | None = None
    order_access_proof_ttl_seconds: int = Field(default=30, ge=1, le=60)
    order_access_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_order_topic: str = "fastapi-platform.order.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_group: str = "shipping-service.order"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_consumer_enabled: bool = False
    kafka_publisher_enabled: bool = False
    kafka_topic: str = "fastapi-platform.shipping.events.v1"
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="SHIPPING_", extra="ignore")

    @model_validator(mode="after")
    def reject_local_development_credentials(self) -> Settings:
        reject_known_local_development_credentials(
            environment=self.environment,
            service_name=self.service_name,
            values={
                "jwt_secret": self.jwt_secret,
                "order_internal_access_secret": self.order_internal_access_secret,
            },
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
