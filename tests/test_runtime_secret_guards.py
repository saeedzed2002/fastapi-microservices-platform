import pytest
from pydantic import ValidationError

from cart_service.config import Settings as CartSettings
from catalog_service.config import Settings as CatalogSettings
from chat_service.config import Settings as ChatSettings
from customer_service.config import Settings as CustomerSettings
from identity_service.config import Settings as IdentitySettings
from inventory_service.config import Settings as InventorySettings
from media_service.config import Settings as MediaSettings
from order_service.config import Settings as OrderSettings
from payment_service.config import Settings as PaymentSettings

LOCAL_JWT_SECRET = "local-development-jwt-secret-change-me-32-bytes"
LOCAL_SESSION_METADATA_SECRET = "local-development-session-metadata-secret-change-me"
LOCAL_CHAT_MEDIA_SECRET = "local-development-chat-media-access-secret-change-me-32-bytes"
LOCAL_CATALOG_MEDIA_SECRET = "local-development-catalog-media-access-secret-change-me-32-bytes"
LOCAL_S3_SECRET = "minio-local-only"
LOCAL_RABBITMQ_URL = "amqp://platform:platform-local-only@localhost:5672//"

UNSAFE_SETTINGS = (
    (IdentitySettings, "jwt_secret", LOCAL_JWT_SECRET),
    (IdentitySettings, "session_metadata_hmac_secret", LOCAL_SESSION_METADATA_SECRET),
    (CustomerSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (CatalogSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (CatalogSettings, "media_internal_access_secret", LOCAL_CATALOG_MEDIA_SECRET),
    (MediaSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (MediaSettings, "s3_secret_access_key", LOCAL_S3_SECRET),
    (MediaSettings, "chat_access_secret", LOCAL_CHAT_MEDIA_SECRET),
    (MediaSettings, "catalog_access_secret", LOCAL_CATALOG_MEDIA_SECRET),
    (MediaSettings, "rabbitmq_url", LOCAL_RABBITMQ_URL),
    (InventorySettings, "jwt_secret", LOCAL_JWT_SECRET),
    (CartSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (OrderSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (OrderSettings, "s3_secret_access_key", LOCAL_S3_SECRET),
    (OrderSettings, "rabbitmq_url", LOCAL_RABBITMQ_URL),
    (PaymentSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (ChatSettings, "jwt_secret", LOCAL_JWT_SECRET),
    (ChatSettings, "media_internal_access_secret", LOCAL_CHAT_MEDIA_SECRET),
)


@pytest.mark.parametrize(("settings_type", "field_name", "value"), UNSAFE_SETTINGS)
def test_each_service_rejects_known_local_credentials_outside_local_development(
    settings_type: type[object], field_name: str, value: str
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        settings_type(environment="production", **{field_name: value})  # type: ignore[operator]


@pytest.mark.parametrize(("settings_type", "field_name", "value"), UNSAFE_SETTINGS)
def test_each_service_keeps_known_defaults_available_for_local_development(
    settings_type: type[object], field_name: str, value: str
) -> None:
    settings_type(environment="local", **{field_name: value})  # type: ignore[operator]
