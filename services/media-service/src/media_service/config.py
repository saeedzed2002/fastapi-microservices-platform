from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "media-service"
    service_version: str = "0.4.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://media_service:media-local-only@localhost:5432/media_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    log_level: str = "INFO"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minio-local"
    s3_secret_access_key: str = "minio-local-only"
    s3_bucket: str = "fastapi-platform-media"
    s3_region: str = "us-east-1"
    upload_url_ttl_seconds: int = Field(default=300, ge=60, le=3600)
    chat_access_secret: str = Field(
        default="local-development-chat-media-access-secret-change-me-32-bytes", min_length=32
    )
    chat_access_previous_secret: str | None = None
    chat_access_proof_max_ttl_seconds: int = Field(default=60, ge=1, le=300)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    rabbitmq_url: str = "amqp://platform:platform-local-only@localhost:5672//"
    task_dispatcher_enabled: bool = False
    task_dispatcher_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.media.events.v1"
    kafka_publisher_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)

    model_config = SettingsConfigDict(env_prefix="MEDIA_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
