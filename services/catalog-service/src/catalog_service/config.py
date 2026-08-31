from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_auth import reject_known_local_development_credentials


class Settings(BaseSettings):
    service_name: str = "catalog-service"
    service_version: str = "0.4.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://catalog_service:catalog-local-only@localhost:5432/catalog_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_topic: str = "fastapi-platform.catalog.events.v1"
    kafka_publisher_enabled: bool = False
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1)
    outbox_claim_lease_seconds: float = Field(default=60.0, ge=1.0, le=900.0)
    media_base_url: str = "http://localhost:8004"
    media_internal_access_secret: str = Field(
        default="local-development-catalog-media-access-secret-change-me-32-bytes",
        min_length=32,
    )
    media_access_proof_ttl_seconds: int = Field(default=60, ge=1, le=300)
    media_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="CATALOG_", extra="ignore")

    @model_validator(mode="after")
    def reject_local_development_credentials(self) -> Settings:
        reject_known_local_development_credentials(
            environment=self.environment,
            service_name=self.service_name,
            values={
                "jwt_secret": self.jwt_secret,
                "media_internal_access_secret": self.media_internal_access_secret,
            },
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
