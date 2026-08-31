import pytest

from platform_auth import reject_known_local_development_credentials


def test_known_local_development_credentials_are_allowed_only_locally() -> None:
    reject_known_local_development_credentials(
        environment="local",
        service_name="identity-service",
        values={"jwt_secret": "local-development-jwt-secret-change-me-32-bytes"},
    )


def test_known_local_development_credentials_fail_without_exposing_the_value() -> None:
    with pytest.raises(ValueError, match="identity-service") as error:
        reject_known_local_development_credentials(
            environment="production",
            service_name="identity-service",
            values={"jwt_secret": "local-development-jwt-secret-change-me-32-bytes"},
        )

    assert "jwt_secret" in str(error.value)
    assert "local-development-jwt-secret-change-me-32-bytes" not in str(error.value)


def test_non_local_credential_value_is_accepted_outside_local_development() -> None:
    reject_known_local_development_credentials(
        environment="production",
        service_name="identity-service",
        values={"jwt_secret": "production-secret-that-is-not-a-known-default"},
    )
