from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_auth import reject_known_local_development_credentials


class Settings(BaseSettings):
    service_name: str = "order-service"
    service_version: str = "0.9.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://order_service:order-local-only@localhost:5432/order_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    catalog_base_url: str = "http://localhost:8003"
    customer_base_url: str = "http://localhost:8002"
    cart_base_url: str = "http://localhost:8005"
    payment_base_url: str = "http://localhost:8006"
    checkout_request_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    checkout_redirect_wait_seconds: float = Field(default=10.0, ge=0.1, le=30.0)
    checkout_redirect_poll_interval_seconds: float = Field(default=0.2, ge=0.05, le=2.0)
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.order.events.v1"
    kafka_dead_letter_topic: str = "fastapi-platform.dead-letter.v1"
    kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)
    kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)
    kafka_publisher_enabled: bool = False
    kafka_consumer_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    invoice_consumer_enabled: bool = False
    task_dispatcher_enabled: bool = False
    task_dispatcher_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    invoice_processing_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    rabbitmq_url: str = "amqp://platform:platform-local-only@localhost:5672//"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minio-local"
    s3_secret_access_key: str = "minio-local-only"
    s3_bucket: str = "fastapi-platform-invoices"
    s3_region: str = "us-east-1"

    model_config = SettingsConfigDict(env_prefix="ORDER_", extra="ignore")

    @model_validator(mode="after")
    def reject_local_development_credentials(self) -> Settings:
        reject_known_local_development_credentials(
            environment=self.environment,
            service_name=self.service_name,
            values={
                "jwt_secret": self.jwt_secret,
                "s3_secret_access_key": self.s3_secret_access_key,
                "rabbitmq_url": self.rabbitmq_url,
            },
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
