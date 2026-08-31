"""Runtime configuration guards for shared authentication material."""

from collections.abc import Mapping
from typing import Final

KNOWN_LOCAL_DEVELOPMENT_CREDENTIALS: Final = frozenset(
    {
        "local-development-jwt-secret-change-me-32-bytes",
        "local-development-session-metadata-secret-change-me",
        "local-development-chat-media-access-secret-change-me-32-bytes",
        "local-development-catalog-media-access-secret-change-me-32-bytes",
        "minio-local-only",
        "amqp://platform:platform-local-only@localhost:5672//",
    }
)


def reject_known_local_development_credentials(
    *,
    environment: str,
    service_name: str,
    values: Mapping[str, str | None],
) -> None:
    """Reject public local credentials before a non-local process can start."""
    if environment.strip().lower() == "local":
        return

    unsafe_fields = sorted(
        field_name
        for field_name, value in values.items()
        if value in KNOWN_LOCAL_DEVELOPMENT_CREDENTIALS
    )
    if unsafe_fields:
        fields = ", ".join(unsafe_fields)
        raise ValueError(
            f"{service_name} must override local-development credentials outside "
            f"local development: {fields}"
        )
