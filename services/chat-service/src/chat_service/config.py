from functools import lru_cache
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "chat-service"
    service_version: str = "0.7.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://chat_service:chat-local-only@localhost:5432/chat_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    media_base_url: str = "http://localhost:8004"
    media_internal_access_secret: str = Field(
        default="local-development-chat-media-access-secret-change-me-32-bytes", min_length=32
    )
    media_internal_access_previous_secret: str | None = None
    media_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_channel: str = "fastapi-platform:chat:messages:v1"
    redis_instance_id: str = Field(
        default_factory=lambda: str(uuid4()), min_length=1, max_length=128
    )
    redis_subscriber_retry_seconds: float = Field(default=0.25, gt=0, le=10)
    redis_subscriber_max_retry_seconds: float = Field(default=5.0, gt=0, le=60)
    presence_ttl_seconds: int = Field(default=75, ge=10, le=3600)
    presence_refresh_seconds: int = Field(default=25, ge=1, le=1800)
    websocket_auth_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    websocket_max_frame_bytes: int = Field(default=16_384, ge=1024, le=1_048_576)
    websocket_connection_rate_limit: int = Field(default=20, ge=1, le=1000)
    websocket_connection_rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="CHAT_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
