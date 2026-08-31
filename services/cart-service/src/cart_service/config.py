from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from platform_auth import reject_known_local_development_credentials


class Settings(BaseSettings):
    service_name: str = "cart-service"
    service_version: str = "0.4.0"
    environment: str = "local"
    database_url: str = (
        "postgresql+asyncpg://cart_service:cart-local-only@localhost:5432/cart_service"
    )
    jwt_secret: str = Field(
        default="local-development-jwt-secret-change-me-32-bytes", min_length=32
    )
    jwt_issuer: str = "fastapi-platform.identity"
    jwt_audience: str = "fastapi-platform"
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_enabled: bool = True
    cart_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="CART_", extra="ignore")

    @model_validator(mode="after")
    def reject_local_development_credentials(self) -> Settings:
        reject_known_local_development_credentials(
            environment=self.environment,
            service_name=self.service_name,
            values={"jwt_secret": self.jwt_secret},
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
