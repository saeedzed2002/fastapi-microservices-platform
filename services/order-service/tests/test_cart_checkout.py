import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from order_service.application import wait_for_payment_pending
from order_service.cart_gateway import (
    CartGatewayUnavailable,
    EmptyCart,
    parse_cart_checkout_snapshot,
)
from order_service.main import app
from order_service.models import Order
from order_service.payment_gateway import (
    PaymentGatewayUnavailable,
    parse_payment_redirect,
)


def test_cart_snapshot_accepts_quantities_and_rejects_bad_payloads() -> None:
    variant_id = uuid4()
    snapshot = parse_cart_checkout_snapshot(
        {"version": 3, "items": [{"variant_id": str(variant_id), "quantity": 2}]}
    )

    assert snapshot.version == 3
    assert snapshot.item_quantities == {variant_id: 2}
    with pytest.raises(EmptyCart):
        parse_cart_checkout_snapshot({"version": 3, "items": []})
    with pytest.raises(CartGatewayUnavailable):
        parse_cart_checkout_snapshot(
            {
                "version": 3,
                "items": [
                    {"variant_id": str(variant_id), "quantity": 1},
                    {"variant_id": str(variant_id), "quantity": 1},
                ],
            }
        )


def test_payment_redirect_requires_a_https_url_and_expiry() -> None:
    redirect = parse_payment_redirect(
        {
            "redirect_url": "https://sandbox.zarinpal.com/pg/StartPay/S123",
            "expires_at": "2026-08-29T15:00:00+00:00",
        }
    )

    assert redirect.redirect_url.endswith("S123")
    with pytest.raises(PaymentGatewayUnavailable):
        parse_payment_redirect(
            {"redirect_url": "http://sandbox.zarinpal.com/pg/StartPay/S123", "expires_at": "bad"}
        )


def test_cart_checkout_route_is_present_in_order_openapi() -> None:
    route = app.openapi()["paths"]["/api/v1/orders/cart/zarinpal"]["post"]

    assert route["responses"]["200"]["description"] == "Successful Response"
    assert "Idempotency-Key" in str(route["parameters"])


def test_payment_ready_wait_reads_durable_state_without_sleeping() -> None:
    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, _: type[Order], __: object) -> Order:
            now = datetime.now(UTC)
            return Order(
                id=uuid4(),
                status="PAYMENT_PENDING",
                tracking_code="ORD-READY",
                currency="IRT",
                total_amount=150000,
                created_at=now,
                updated_at=now,
            )

        async def scalars(self, _: object) -> list[object]:
            return []

    class SessionFactory:
        def __call__(self) -> Session:
            return Session()

    async def exercise() -> None:
        response = await wait_for_payment_pending(
            session_factory=SessionFactory(),  # type: ignore[arg-type]
            order_id=uuid4(),
            timeout_seconds=1,
            poll_interval_seconds=0.1,
        )
        assert response is not None
        assert response.status == "PAYMENT_PENDING"

    asyncio.run(exercise())
