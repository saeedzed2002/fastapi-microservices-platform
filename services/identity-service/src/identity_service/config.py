from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "identity-service"
    service_version: str = "0.3.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://identity_service:identity-local-only@localhost:5432/identity_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2_592_000
    session_metadata_hmac_secret: str = Field(
        default="local-development-session-metadata-secret-change-me", min_length=32
    )
    otp_redis_url: str = "redis://localhost:6379/1"
    otp_code_ttl_seconds: int = Field(default=300, ge=60, le=1800)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=15, le=600)
    otp_max_verify_attempts: int = Field(default=5, ge=1, le=10)
    otp_phone_rate_limit: int = Field(default=5, ge=1, le=20)
    otp_phone_rate_window_seconds: int = Field(default=3600, ge=60, le=86_400)
    password_reset_redis_url: str = "redis://localhost:6379/1"
    password_reset_token_ttl_seconds: int = Field(default=900, ge=300, le=3600)
    password_reset_resend_cooldown_seconds: int = Field(default=60, ge=15, le=600)
    staff_login_max_failures: int = Field(default=5, ge=1, le=20)
    staff_login_failure_window_seconds: int = Field(default=900, ge=60, le=86_400)
    staff_login_lockout_seconds: int = Field(default=900, ge=60, le=86_400)
    otp_notification_base_url: str = "http://localhost:8007"
    otp_notification_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    internal_otp_shared_secret: str | None = Field(default=None, min_length=32)
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.identity.events.v1"
    kafka_publisher_enabled: bool = False
    outbox_poll_interval_seconds: float = 1.0
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="IDENTITY_", extra="ignore")

    @field_validator("internal_otp_shared_secret", mode="before")
    @classmethod
    def empty_internal_otp_secret_is_unconfigured(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
