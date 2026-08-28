from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from order_service.application import (
    InvalidOrderCursor,
    checkout_total,
    decode_order_cursor,
    encode_order_cursor,
    required_customer_email,
    transition_order,
    validate_checkout_payment,
)
from order_service.models import Order, OrderItem
from order_service.workers.invoice_tasks import render_invoice_pdf


def test_checkout_total_is_exact_decimal() -> None:
    assert checkout_total([(Decimal("1.25"), 2), (Decimal("2.50"), 1)]) == Decimal("5.00")


def test_illegal_transition_is_ignored() -> None:
    order = Order(status="PENDING", tracking_code="ORD-TEST", currency="USD", total_amount=1)
    assert not transition_order(
        order, event_type="payment.succeeded.v1", event_id=__import__("uuid").uuid4(), reason=""
    )
    assert order.status == "PENDING"


def test_checkout_success_transitions_are_ordered() -> None:
    order = Order(status="PENDING", tracking_code="ORD-TEST", currency="USD", total_amount=1)

    assert transition_order(order, event_type="inventory.reserved.v1", event_id=uuid4(), reason="")
    assert order.status == "INVENTORY_RESERVED"
    assert transition_order(order, event_type="payment.processing.v1", event_id=uuid4(), reason="")
    assert transition_order(order, event_type="payment.succeeded.v1", event_id=uuid4(), reason="")
    assert order.status == "CONFIRMED"


def test_late_payment_success_cannot_resurrect_cancelled_order() -> None:
    order = Order(
        status="PAYMENT_PENDING", tracking_code="ORD-TEST", currency="USD", total_amount=1
    )

    assert transition_order(order, event_type="payment.failed.v1", event_id=uuid4(), reason="")
    assert order.status == "CANCELLED"
    assert not transition_order(
        order, event_type="payment.succeeded.v1", event_id=uuid4(), reason=""
    )
    assert order.status == "CANCELLED"


def test_invoice_pdf_is_rendered_from_order_snapshot() -> None:
    order = Order(
        tracking_code="ORD-TEST",
        currency="USD",
        total_amount=Decimal("10.00"),
        customer_email="customer@example.test",
    )
    item = OrderItem(
        order_id=uuid4(),
        variant_id=uuid4(),
        sku="SKU-TEST",
        product_name="Test product",
        unit_amount=Decimal("5.00"),
        quantity=2,
    )

    pdf = render_invoice_pdf(order=order, items=[item])

    assert pdf.startswith(b"%PDF")


def test_order_cursor_round_trips_and_rejects_invalid_input() -> None:
    order = Order(status="PENDING", tracking_code="ORD-TEST", currency="USD", total_amount=1)
    order.id = uuid4()
    order.created_at = datetime.now(UTC)

    created_at, order_id = decode_order_cursor(encode_order_cursor(order))

    assert created_at == order.created_at
    assert order_id == order.id
    with pytest.raises(InvalidOrderCursor):
        decode_order_cursor("not-a-valid-cursor")


def test_checkout_requires_a_real_customer_contact_email() -> None:
    assert required_customer_email({"email": "customer@example.com"}) == "customer@example.com"

    with pytest.raises(HTTPException, match="checkout email unavailable"):
        required_customer_email({"email": None})


def test_zarinpal_checkout_requires_a_whole_irt_amount() -> None:
    validate_checkout_payment(
        payment_method="zarinpal", currency="IRT", total_amount=Decimal("150000")
    )

    with pytest.raises(HTTPException, match="zarinpal requires IRT currency"):
        validate_checkout_payment(
            payment_method="zarinpal", currency="USD", total_amount=Decimal("150000")
        )
    with pytest.raises(HTTPException, match="zarinpal amount must be a positive whole IRT value"):
        validate_checkout_payment(
            payment_method="zarinpal", currency="IRT", total_amount=Decimal("150000.50")
        )
