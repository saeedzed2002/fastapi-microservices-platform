import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from payment_service.application import (
    PaymentRequestInProgress,
    _prepare_zarinpal_request,
    _record_zarinpal_cancellation,
    start_zarinpal_payment,
)
from payment_service.zarinpal import (
    ZarinpalClient,
    ZarinpalNotConfigured,
    ZarinpalRejected,
    ZarinpalUnavailable,
)


def test_zarinpal_sandbox_request_and_verify_use_v4_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/request.json"):
            return httpx.Response(200, json={"data": {"code": 100, "authority": "S000000000"}})
        return httpx.Response(200, json={"data": {"code": 101, "ref_id": 987654321}})

    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="00000000-0000-0000-0000-000000000000",
            sandbox=True,
            callback_url="https://localhost/api/v1/payments/zarinpal/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
        request = await client.create_payment(amount=150000, description="Order test")
        verification = await client.verify_payment(amount=150000, authority=request.authority)

        assert request.authority == "S000000000"
        assert request.redirect_url == "https://sandbox.zarinpal.com/pg/StartPay/S000000000"
        assert verification.succeeded
        assert verification.reference_id == "987654321"

    asyncio.run(exercise())

    assert [request.url.path for request in requests] == [
        "/pg/v4/payment/request.json",
        "/pg/v4/payment/verify.json",
    ]
    request_payload = json.loads(requests[0].content)
    assert request_payload == {
        "merchant_id": "00000000-0000-0000-0000-000000000000",
        "amount": 150000,
        "callback_url": "https://localhost/api/v1/payments/zarinpal/callback",
        "description": "Order test",
    }


def test_zarinpal_reverse_uses_the_documented_v4_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"code": 100}})

    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="00000000-0000-0000-0000-000000000000",
            sandbox=True,
            callback_url="https://localhost/api/v1/payments/zarinpal/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
        result = await client.reverse_payment(authority="S000000000")
        assert result.code == "100"

    asyncio.run(exercise())

    assert requests[0].url.path == "/pg/v4/payment/reverse.json"
    assert json.loads(requests[0].content) == {
        "merchant_id": "00000000-0000-0000-0000-000000000000",
        "authority": "S000000000",
    }


def test_zarinpal_rejection_does_not_become_a_success() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"code": -9}})

    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="merchant",
            sandbox=False,
            callback_url="https://example.test/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ZarinpalRejected, match="-9"):
            await client.create_payment(amount=1, description="Order test")

    asyncio.run(exercise())


def test_zarinpal_requires_explicit_merchant_configuration() -> None:
    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="",
            sandbox=True,
            callback_url="https://localhost/callback",
            timeout_seconds=10,
        )
        with pytest.raises(ZarinpalNotConfigured):
            await client.create_payment(amount=1, description="Order test")

    asyncio.run(exercise())


def test_zarinpal_transport_failure_has_a_safe_reason() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed")

    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="merchant",
            sandbox=True,
            callback_url="https://localhost/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(ZarinpalUnavailable, match="network_request_error"):
            await client.create_payment(amount=1, description="Order test")

    asyncio.run(exercise())


def test_missing_merchant_does_not_create_a_requesting_attempt() -> None:
    async def exercise() -> None:
        client = ZarinpalClient(
            merchant_id="",
            sandbox=True,
            callback_url="https://localhost/callback",
            timeout_seconds=10,
        )
        db = SimpleNamespace(scalar=AsyncMock(), commit=AsyncMock())

        with pytest.raises(ZarinpalNotConfigured):
            await start_zarinpal_payment(
                db,
                order_id=uuid4(),
                provider=client,
                expected_currency="IRT",
            )

        db.scalar.assert_not_awaited()
        db.commit.assert_not_awaited()

    asyncio.run(exercise())


def test_requesting_authority_is_recovered_without_a_second_provider_request() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            status="AWAITING_CUSTOMER",
            method="zarinpal",
            currency="IRT",
            amount=Decimal("150000"),
            provider_reference="zarinpal-pending-test",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        attempt = SimpleNamespace(status="REQUESTING", authority="S000000000")
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[intent, attempt]),
            add=Mock(),
            commit=AsyncMock(),
        )

        recovered_intent, authority = await _prepare_zarinpal_request(
            db,
            order_id=intent.order_id,
            expected_currency="IRT",
        )

        assert recovered_intent is intent
        assert authority == "S000000000"
        assert attempt.status == "PENDING_CUSTOMER"
        assert intent.status == "PENDING_CUSTOMER"
        assert intent.provider_reference == "zarinpal:S000000000"
        db.add.assert_not_called()

    asyncio.run(exercise())


def test_new_zarinpal_request_marks_intent_requesting_before_provider_call() -> None:
    async def exercise() -> None:
        intent = SimpleNamespace(
            id=uuid4(),
            order_id=uuid4(),
            status="AWAITING_CUSTOMER",
            method="zarinpal",
            currency="IRT",
            amount=Decimal("150000"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[intent, None]),
            add=Mock(),
            commit=AsyncMock(),
        )

        prepared_intent, authority = await _prepare_zarinpal_request(
            db,
            order_id=intent.order_id,
            expected_currency="IRT",
        )

        assert prepared_intent is intent
        assert authority is None
        assert intent.status == "REQUESTING"
        db.add.assert_called_once()

    asyncio.run(exercise())


def test_zarinpal_cancellation_does_not_overwrite_verification_in_progress() -> None:
    async def exercise() -> None:
        attempt = SimpleNamespace(id=uuid4(), intent_id=uuid4(), status="VERIFYING")
        intent = SimpleNamespace(
            id=attempt.intent_id,
            order_id=uuid4(),
            provider_reference="zarinpal:authority",
            status="VERIFYING",
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[attempt, intent]),
            commit=AsyncMock(),
        )

        with pytest.raises(PaymentRequestInProgress):
            await _record_zarinpal_cancellation(db, attempt.id)

        assert attempt.status == "VERIFYING"
        assert intent.status == "VERIFYING"
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_zarinpal_cancellation_reopens_only_pending_customer_attempt() -> None:
    async def exercise() -> None:
        attempt = SimpleNamespace(id=uuid4(), intent_id=uuid4(), status="PENDING_CUSTOMER")
        intent = SimpleNamespace(
            id=attempt.intent_id,
            order_id=uuid4(),
            provider_reference="zarinpal:authority",
            status="PENDING_CUSTOMER",
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[attempt, intent]),
            commit=AsyncMock(),
        )

        result = await _record_zarinpal_cancellation(db, attempt.id)

        assert result.payment_status == "cancelled"
        assert attempt.status == "CANCELLED"
        assert intent.status == "AWAITING_CUSTOMER"
        db.commit.assert_awaited_once()

    asyncio.run(exercise())
