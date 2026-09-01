import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from order_service.application import (
    InvalidOrderCursor,
    authorize_fulfillment_transition,
    checkout_total,
    decode_order_cursor,
    encode_order_cursor,
    process_saga_result,
    process_shipping_status_update,
    receive_order_return,
    request_order_refund,
    required_customer_email,
    transition_order,
    update_order_fulfillment,
    validate_checkout_payment,
)
from order_service.models import (
    FulfillmentAuthorization,
    Order,
    OrderItem,
    OrderRefundRequest,
    OrderReturnRequest,
    OutboxMessage,
)
from order_service.schemas import (
    FulfillmentUpdateRequest,
    ShippingCommandRecoveryResponse,
)
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


def test_refund_saga_transitions_cannot_interleave_with_fulfillment() -> None:
    order = Order(status="REFUND_PENDING", tracking_code="ORD-TEST", currency="IRT", total_amount=1)

    assert transition_order(order, event_type="payment.refunded.v1", event_id=uuid4(), reason="")
    assert order.status == "REFUNDED"
    assert not transition_order(
        order, event_type="payment.refund_failed.v1", event_id=uuid4(), reason=""
    )

    failed = Order(
        status="REFUND_PENDING", tracking_code="ORD-FAIL", currency="IRT", total_amount=1
    )
    assert transition_order(
        failed, event_type="payment.refund_failed.v1", event_id=uuid4(), reason=""
    )
    assert failed.status == "CONFIRMED"


def test_refund_failure_does_not_create_a_second_order_confirmation_event() -> None:
    async def exercise() -> None:
        order = Order(
            status="REFUND_PENDING", tracking_code="ORD-FAIL", currency="IRT", total_amount=1
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, order]),
            add=Mock(),
            commit=AsyncMock(),
        )
        envelope = {
            "event_id": str(uuid4()),
            "event_type": "payment.refund_failed.v1",
            "payload": {"order_id": str(uuid4())},
        }

        assert await process_saga_result(db, envelope)
        assert order.status == "CONFIRMED"
        assert not any(isinstance(call.args[0], OutboxMessage) for call in db.add.call_args_list)

    asyncio.run(exercise())


def test_post_delivery_return_receipt_creates_physical_and_financial_handoffs() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        customer_id = uuid4()
        administrator_id = uuid4()
        order = Order(
            customer_id=customer_id,
            status="DELIVERED",
            tracking_code="ORD-RETURN",
            currency="IRT",
            total_amount=1,
            payment_method="test_success",
        )
        order.id = uuid4()
        item = OrderItem(
            order_id=order.id,
            variant_id=uuid4(),
            sku="SKU-RETURN",
            product_name="Returnable item",
            unit_amount=1,
            quantity=1,
            attributes={},
        )
        return_request = OrderReturnRequest(
            order_id=order.id,
            idempotency_key="return-request-key",
            requested_by=customer_id,
            reason="not suitable",
            status="APPROVED",
            decision_idempotency_key="return-decision-key",
            decided_by=administrator_id,
            decided_at=now,
            created_at=now,
            updated_at=now,
        )
        return_request.id = uuid4()
        added: list[object] = []

        def add(value: object) -> None:
            if isinstance(value, OrderRefundRequest):
                value.id = uuid4()
            added.append(value)

        db = SimpleNamespace(
            scalar=AsyncMock(
                side_effect=[
                    return_request,
                    None,
                    order,
                    order,
                    None,
                    return_request,
                    None,
                ]
            ),
            scalars=AsyncMock(return_value=[item]),
            add=Mock(side_effect=add),
            flush=AsyncMock(),
            commit=AsyncMock(),
        )

        response = await receive_order_return(
            db,
            return_request_id=return_request.id,
            received_by=administrator_id,
            idempotency_key="return-receipt-key",
            allow_test_refund=True,
            now=now,
        )

        assert response.status == "REFUND_PENDING"
        assert order.status == "REFUND_PENDING"
        assert return_request.received_at == now
        assert return_request.receipt_idempotency_key == "return-receipt-key"
        outbox = [row for row in added if isinstance(row, OutboxMessage)]
        assert [row.event_type for row in outbox] == [
            "order.return_received.v1",
            "order.refund_requested.v1",
        ]
        assert outbox[0].payload["items"] == [{"sku": "SKU-RETURN", "quantity": 1}]
        assert outbox[1].payload["return_request_id"] == str(return_request.id)

    asyncio.run(exercise())


def test_return_refund_failure_restores_delivered_status_and_marks_return() -> None:
    async def exercise() -> None:
        order = Order(
            status="REFUND_PENDING", tracking_code="ORD-RETURN-FAIL", currency="IRT", total_amount=1
        )
        order.id = uuid4()
        return_request = OrderReturnRequest(
            order_id=order.id,
            idempotency_key="return-request-key",
            requested_by=uuid4(),
            reason="not suitable",
            status="REFUND_PENDING",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return_request.id = uuid4()
        refund_request = OrderRefundRequest(
            order_id=order.id,
            idempotency_key="return-refund-key",
            requested_by=uuid4(),
            return_request_id=return_request.id,
            pre_refund_status="DELIVERED",
        )
        refund_request.id = uuid4()
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, order, refund_request, return_request]),
            add=Mock(),
            commit=AsyncMock(),
        )
        envelope = {
            "event_id": str(uuid4()),
            "event_type": "payment.refund_failed.v1",
            "payload": {
                "order_id": str(order.id),
                "refund_request_id": str(refund_request.id),
            },
        }

        assert await process_saga_result(db, envelope)
        assert order.status == "DELIVERED"
        assert return_request.status == "REFUND_FAILED"

    asyncio.run(exercise())


def test_refund_pending_order_cannot_enter_fulfillment() -> None:
    async def exercise() -> None:
        order = Order(
            status="REFUND_PENDING", tracking_code="ORD-REFUND", currency="IRT", total_amount=1
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, None, None]),
            add=Mock(),
            commit=AsyncMock(),
        )

        with pytest.raises(HTTPException, match="invalid fulfillment transition"):
            await update_order_fulfillment(
                db,
                order_id=uuid4(),
                updated_by=uuid4(),
                payload=FulfillmentUpdateRequest(status="PROCESSING"),
            )

    asyncio.run(exercise())


def test_shipping_requires_both_tracking_fields() -> None:
    with pytest.raises(ValueError, match="carrier and tracking_number"):
        FulfillmentUpdateRequest(status="SHIPPED")

    shipment = FulfillmentUpdateRequest(status="SHIPPED", carrier="Post", tracking_number="TRK-1")
    assert shipment.tracking_number == "TRK-1"


def test_active_fulfillment_authorization_blocks_refund() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        order = Order(
            status="CONFIRMED",
            tracking_code="ORD-AUTH",
            currency="IRT",
            total_amount=1,
            payment_method="zarinpal",
        )
        order.id = uuid4()
        authorization = FulfillmentAuthorization(
            order_id=order.id,
            command_id=uuid4(),
            from_status="CONFIRMED",
            target_status="SHIPPED",
            requested_by=uuid4(),
            status="ACTIVE",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=30),
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, None, authorization]),
            add=Mock(),
            commit=AsyncMock(),
        )

        with pytest.raises(HTTPException, match="fulfillment transition is already in progress"):
            await request_order_refund(
                db,
                order_id=order.id,
                requested_by=uuid4(),
                idempotency_key="refund-after-shipping-command",
                now=now,
            )

        db.add.assert_not_called()
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_expired_fulfillment_authorization_requires_definitive_shipping_recovery() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        order = Order(
            status="CONFIRMED",
            tracking_code="ORD-EXPIRED-AUTH",
            currency="IRT",
            total_amount=1,
            payment_method="zarinpal",
        )
        order.id = uuid4()
        authorization = FulfillmentAuthorization(
            order_id=order.id,
            command_id=uuid4(),
            from_status="CONFIRMED",
            target_status="SHIPPED",
            requested_by=uuid4(),
            status="ACTIVE",
            issued_at=now - timedelta(seconds=2),
            expires_at=now - timedelta(seconds=1),
        )

        def assign_refund_identifier(value: object) -> None:
            if isinstance(value, OrderRefundRequest):
                value.id = uuid4()

        async def recover(_: FulfillmentAuthorization) -> ShippingCommandRecoveryResponse:
            return ShippingCommandRecoveryResponse(
                command_id=authorization.command_id, state="NOT_COMMITTED"
            )

        db = SimpleNamespace(
            scalar=AsyncMock(
                side_effect=[order, None, authorization, authorization, order, None, None, None]
            ),
            add=Mock(side_effect=assign_refund_identifier),
            flush=AsyncMock(),
            commit=AsyncMock(),
        )

        response = await request_order_refund(
            db,
            order_id=order.id,
            requested_by=uuid4(),
            idempotency_key="refund-after-expired-shipping-command",
            now=now,
            recover_expired_authorization=recover,
        )

        assert response.status == "REFUND_PENDING"
        assert authorization.status == "RELEASED"
        assert authorization.resolved_at == now
        assert db.commit.await_count == 3

    asyncio.run(exercise())


def test_fulfillment_authorization_is_idempotent_for_one_command() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        order = Order(
            status="CONFIRMED",
            tracking_code="ORD-COMMAND",
            currency="IRT",
            total_amount=1,
        )
        order.id = uuid4()
        command_id = uuid4()
        requested_by = uuid4()
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, None, None]),
            add=Mock(),
            flush=AsyncMock(),
            commit=AsyncMock(),
        )

        authorization = await authorize_fulfillment_transition(
            db,
            order_id=order.id,
            command_id=command_id,
            requested_by=requested_by,
            target_status="SHIPPED",
            expires_at=now + timedelta(seconds=30),
            now=now,
        )

        assert authorization.order_id == order.id
        assert authorization.command_id == command_id
        assert authorization.from_status == "CONFIRMED"
        assert authorization.target_status == "SHIPPED"
        assert authorization.status == "ACTIVE"
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()

        replay_authorization = FulfillmentAuthorization(
            order_id=order.id,
            command_id=command_id,
            from_status="CONFIRMED",
            target_status="SHIPPED",
            requested_by=requested_by,
            status="ACTIVE",
            issued_at=now,
            expires_at=now + timedelta(seconds=30),
        )
        replay_db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, replay_authorization, replay_authorization]),
            add=Mock(),
            flush=AsyncMock(),
            commit=AsyncMock(),
        )

        replayed = await authorize_fulfillment_transition(
            replay_db,
            order_id=order.id,
            command_id=command_id,
            requested_by=requested_by,
            target_status="SHIPPED",
            expires_at=now + timedelta(seconds=30),
            now=now,
        )

        assert replayed is replay_authorization
        replay_db.add.assert_not_called()
        replay_db.flush.assert_not_awaited()
        replay_db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_active_fulfillment_authorization_blocks_legacy_mutation() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        order = Order(
            status="CONFIRMED",
            tracking_code="ORD-LEGACY-FENCE",
            currency="IRT",
            total_amount=1,
        )
        order.id = uuid4()
        authorization = FulfillmentAuthorization(
            order_id=order.id,
            command_id=uuid4(),
            from_status="CONFIRMED",
            target_status="SHIPPED",
            requested_by=uuid4(),
            status="ACTIVE",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=30),
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, authorization]),
            add=Mock(),
            commit=AsyncMock(),
        )

        with pytest.raises(HTTPException, match="fulfillment transition is already in progress"):
            await update_order_fulfillment(
                db,
                order_id=order.id,
                updated_by=uuid4(),
                payload=FulfillmentUpdateRequest(status="PROCESSING"),
            )

        db.add.assert_not_called()
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_shipping_status_fact_advances_only_the_matching_authorization() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        order = Order(
            status="CONFIRMED",
            tracking_code="ORD-SHIPPING-EVENT",
            currency="IRT",
            total_amount=1,
        )
        order.id = uuid4()
        authorization = FulfillmentAuthorization(
            order_id=order.id,
            command_id=uuid4(),
            from_status="CONFIRMED",
            target_status="SHIPPED",
            requested_by=uuid4(),
            status="ACTIVE",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=10),
        )
        authorization.id = uuid4()
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, order, authorization, None]),
            add=Mock(),
            commit=AsyncMock(),
        )
        accepted = await process_shipping_status_update(
            db,
            {
                "event_id": str(uuid4()),
                "event_type": "shipping.status_updated.v1",
                "payload": {
                    "order_id": str(order.id),
                    "authorization_id": str(authorization.id),
                    "command_id": str(authorization.command_id),
                    "requested_by": str(authorization.requested_by),
                    "status": "SHIPPED",
                    "carrier": "Post",
                    "tracking_number": "TRK-2",
                    "occurred_at": now.isoformat().replace("+00:00", "Z"),
                },
            },
        )

        assert accepted is True
        assert order.status == "SHIPPED"
        assert authorization.status == "CONSUMED"
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


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


def test_online_checkout_requires_a_whole_irt_amount() -> None:
    validate_checkout_payment(
        payment_method="online", currency="IRT", total_amount=Decimal("150000")
    )

    with pytest.raises(HTTPException, match="online requires IRT currency"):
        validate_checkout_payment(
            payment_method="online", currency="USD", total_amount=Decimal("150000")
        )
