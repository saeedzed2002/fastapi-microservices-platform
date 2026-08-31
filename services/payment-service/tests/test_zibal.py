import asyncio
import json

import httpx
import pytest

from payment_service.zibal import (
    ZibalClient,
    ZibalNotConfigured,
    ZibalRejected,
    ZibalUnavailable,
)


def test_zibal_request_and_verify_use_documented_provider_shape() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/request"):
            return httpx.Response(200, json={"result": 100, "trackId": 1533727744287})
        return httpx.Response(200, json={"result": 100, "status": 1})

    async def exercise() -> None:
        client = ZibalClient(
            merchant_id="zibal-test-merchant",
            callback_url="https://localhost/api/v1/payments/zibal/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
        payment = await client.create_payment(amount=150000, description="Order test")
        verification = await client.verify_payment(amount=150000, track_id=payment.track_id)

        assert payment.track_id == "1533727744287"
        assert payment.redirect_url == "https://gateway.zibal.ir/v1/start/1533727744287"
        assert verification.succeeded

    asyncio.run(exercise())

    assert [request.url.path for request in requests] == ["/v1/request", "/v1/verify"]
    assert json.loads(requests[0].content) == {
        "merchant": "zibal-test-merchant",
        "callbackUrl": "https://localhost/api/v1/payments/zibal/callback",
        "amount": 150000,
        "description": "Order test",
    }
    assert json.loads(requests[1].content) == {
        "merchant": "zibal-test-merchant",
        "trackId": 1533727744287,
    }


def test_zibal_rejection_and_missing_configuration_are_explicit() -> None:
    async def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": 103})

    async def exercise() -> None:
        client = ZibalClient(
            merchant_id="merchant",
            callback_url="https://example.test/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(rejected),
        )
        with pytest.raises(ZibalRejected, match="103"):
            await client.create_payment(amount=150000, description="Order test")

        unconfigured = ZibalClient(
            merchant_id="",
            callback_url="https://example.test/callback",
            timeout_seconds=10,
        )
        with pytest.raises(ZibalNotConfigured):
            await unconfigured.create_payment(amount=150000, description="Order test")

    asyncio.run(exercise())


def test_zibal_transport_failure_has_a_safe_reason() -> None:
    async def unavailable(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed")

    async def exercise() -> None:
        client = ZibalClient(
            merchant_id="merchant",
            callback_url="https://example.test/callback",
            timeout_seconds=10,
            transport=httpx.MockTransport(unavailable),
        )
        with pytest.raises(ZibalUnavailable, match="network_request_error"):
            await client.create_payment(amount=150000, description="Order test")

    asyncio.run(exercise())
