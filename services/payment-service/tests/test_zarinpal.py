import asyncio
import json

import httpx
import pytest

from payment_service.zarinpal import (
    ZarinpalClient,
    ZarinpalNotConfigured,
    ZarinpalRejected,
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
