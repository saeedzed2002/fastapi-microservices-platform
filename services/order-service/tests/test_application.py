from decimal import Decimal
from uuid import uuid4

from order_service.application import checkout_total, transition_order
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
