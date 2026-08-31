import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from payment_service.application import start_online_payment
from payment_service.zarinpal import ZarinpalClient, ZarinpalUnavailable
from payment_service.zibal import ZibalClient


def _online_intent() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        order_id=uuid4(),
        method="online",
        status="AWAITING_CUSTOMER",
        currency="IRT",
        amount=Decimal("150000"),
        provider_reference="online-pending-test",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


def test_online_payment_falls_back_only_after_a_definitive_zarinpal_rejection() -> None:
    async def zarinpal_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"code": -9}})

    async def zibal_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/request"
        return httpx.Response(200, json={"result": 100, "trackId": 1533727744287})

    async def exercise() -> None:
        intent = _online_intent()
        zarinpal_attempt = SimpleNamespace(
            id=uuid4(), provider="zarinpal", status="REQUESTING", authority=None
        )
        zibal_attempt = SimpleNamespace(
            id=uuid4(), provider="zibal", status="REQUESTING", authority=None
        )
        db = SimpleNamespace(
            scalar=AsyncMock(
                side_effect=[
                    intent,
                    None,
                    zarinpal_attempt,
                    intent,
                    zarinpal_attempt,
                    intent,
                    None,
                    zibal_attempt,
                    intent,
                    zibal_attempt,
                ]
            ),
            add=Mock(),
            commit=AsyncMock(),
        )
        result = await start_online_payment(
            db,
            order_id=intent.order_id,
            zarinpal=ZarinpalClient(
                merchant_id="merchant",
                sandbox=True,
                callback_url="https://localhost/api/v1/payments/zarinpal/callback",
                timeout_seconds=10,
                transport=httpx.MockTransport(zarinpal_handler),
            ),
            zibal=ZibalClient(
                merchant_id="zibal-merchant",
                callback_url="https://localhost/api/v1/payments/zibal/callback",
                timeout_seconds=10,
                transport=httpx.MockTransport(zibal_handler),
            ),
            expected_currency="IRT",
        )

        assert result.provider == "zibal"
        assert zarinpal_attempt.status == "REJECTED"
        assert zarinpal_attempt.failure_code == "-9"
        assert zibal_attempt.status == "PENDING_CUSTOMER"
        assert zibal_attempt.authority == "1533727744287"
        assert intent.status == "PENDING_CUSTOMER"
        assert intent.provider_reference == "zibal:1533727744287"

    asyncio.run(exercise())


def test_online_payment_never_falls_back_after_an_unknown_zarinpal_request() -> None:
    zibal_called = False

    async def zarinpal_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed")

    async def zibal_handler(_: httpx.Request) -> httpx.Response:
        nonlocal zibal_called
        zibal_called = True
        return httpx.Response(200, json={"result": 100, "trackId": 1})

    async def exercise() -> None:
        intent = _online_intent()
        attempt = SimpleNamespace(
            id=uuid4(), provider="zarinpal", status="REQUESTING", authority=None
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[intent, None, attempt]),
            add=Mock(),
            commit=AsyncMock(),
        )
        with pytest.raises(ZarinpalUnavailable, match="network_request_error"):
            await start_online_payment(
                db,
                order_id=intent.order_id,
                zarinpal=ZarinpalClient(
                    merchant_id="merchant",
                    sandbox=True,
                    callback_url="https://localhost/api/v1/payments/zarinpal/callback",
                    timeout_seconds=10,
                    transport=httpx.MockTransport(zarinpal_handler),
                ),
                zibal=ZibalClient(
                    merchant_id="zibal-merchant",
                    callback_url="https://localhost/api/v1/payments/zibal/callback",
                    timeout_seconds=10,
                    transport=httpx.MockTransport(zibal_handler),
                ),
                expected_currency="IRT",
            )
        assert intent.status == "REQUESTING"
        assert attempt.status == "REQUESTING"

    asyncio.run(exercise())
    assert not zibal_called
