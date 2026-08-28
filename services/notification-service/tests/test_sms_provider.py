import json
from typing import Any

import pytest

from notification_service.config import Settings
from notification_service.providers import SmsIrBulkProvider, SmsProviderError


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")


def test_smsir_bulk_provider_uses_expected_authenticated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, *, timeout: float) -> FakeResponse:
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["api_key"] = request.headers["X-api-key"]
        captured["timeout"] = timeout
        return FakeResponse({"status": 1, "data": {"messageIds": [12345]}})

    monkeypatch.setattr("notification_service.providers.urlopen", fake_urlopen)
    provider = SmsIrBulkProvider(
        Settings(
            smsir_enabled=True,
            smsir_api_key="test-key",
            smsir_line_number="30001234567",
        )
    )

    receipt = provider.send_otp(phone="989121234567", code="123456")

    assert receipt.provider_message_id == "12345"
    assert captured["payload"] == {
        "lineNumber": 30001234567,
        "MessageText": "کد ورود شما: 123456",
        "Mobiles": ["989121234567"],
        "SendDateTime": None,
    }
    assert captured["api_key"] == "test-key"
    assert captured["timeout"] == 10.0


def test_smsir_bulk_provider_rejects_invalid_line_before_network_call() -> None:
    provider = SmsIrBulkProvider(
        Settings(
            smsir_enabled=True,
            smsir_api_key="test-key",
            smsir_line_number="not-a-number",
        )
    )

    with pytest.raises(SmsProviderError, match="line number"):
        provider.send_otp(phone="989121234567", code="123456")


def test_smsir_bulk_provider_requires_provider_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "notification_service.providers.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"status": 0, "message": "rejected"}),
    )
    provider = SmsIrBulkProvider(
        Settings(
            smsir_enabled=True,
            smsir_api_key="test-key",
            smsir_line_number="30001234567",
        )
    )

    with pytest.raises(SmsProviderError, match="rejected"):
        provider.send_otp(phone="989121234567", code="123456")


def test_empty_internal_otp_secret_is_an_unconfigured_secret() -> None:
    assert Settings(internal_otp_shared_secret="").internal_otp_shared_secret is None
