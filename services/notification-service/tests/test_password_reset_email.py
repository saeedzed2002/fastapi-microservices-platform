import asyncio
from typing import Any
from uuid import UUID

import pytest

from notification_service.config import Settings
from notification_service.identity_gateway import IdentityPasswordResetGateway
from notification_service.models import PasswordResetEmailDelivery


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {
            "email": "admin@example.com",
            "token": "11111111-1111-4111-8111-111111111111.temporary-secret",
        }


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, *, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, path: str, *, headers: dict[str, str]) -> FakeResponse:
        self.calls.append({"path": path, "headers": headers})
        return FakeResponse()


def test_password_reset_gateway_uses_private_authenticated_token_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        FakeAsyncClient.calls.clear()
        monkeypatch.setattr(
            "notification_service.identity_gateway.httpx.AsyncClient",
            FakeAsyncClient,
        )
        delivery_id = UUID("11111111-1111-4111-8111-111111111111")
        gateway = IdentityPasswordResetGateway(
            Settings(internal_otp_shared_secret="internal-secret-at-least-thirty-two-bytes")
        )

        assert await gateway.get_delivery_token(delivery_id) == (
            "admin@example.com",
            "11111111-1111-4111-8111-111111111111.temporary-secret",
        )
        assert FakeAsyncClient.calls == [
            {
                "path": (
                    "/internal/v1/password-reset-deliveries/11111111-1111-4111-8111-111111111111"
                ),
                "headers": {
                    "X-Platform-Internal-Token": "internal-secret-at-least-thirty-two-bytes"
                },
            }
        ]

    asyncio.run(exercise())


def test_password_reset_delivery_model_has_no_raw_token_column() -> None:
    assert "token" not in PasswordResetEmailDelivery.__table__.columns
