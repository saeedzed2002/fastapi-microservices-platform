import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from shipping_service.application import (
    commit_status_transition,
    load_command_recovery,
    process_order_event,
)
from shipping_service.models import OutboxMessage, Shipment, ShipmentTransition
from shipping_service.schemas import ShipmentStatusUpdateRequest


def test_confirmed_order_creates_ready_shipment_and_records_inbox() -> None:
    event_id = uuid4()
    order_id = uuid4()
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )

    accepted = asyncio.run(
        process_order_event(
            db,
            {
                "event_id": str(event_id),
                "event_type": "order.confirmed.v1",
                "payload": {"order_id": str(order_id)},
            },
        )
    )

    assert accepted is True
    assert db.add.call_count == 1
    db.execute.assert_awaited_once()
    statement = db.execute.await_args.args[0]
    rendered = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (order_id) DO NOTHING" in rendered
    db.commit.assert_awaited_once()


def test_duplicate_order_event_is_not_processed_twice() -> None:
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=uuid4()),
        add=Mock(),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )

    accepted = asyncio.run(
        process_order_event(
            db,
            {
                "event_id": str(uuid4()),
                "event_type": "order.confirmed.v1",
                "payload": {"order_id": str(uuid4())},
            },
        )
    )

    assert accepted is False
    db.add.assert_not_called()
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_shipment_transition_writes_a_matching_outbox_fact() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        shipment = Shipment(order_id=order_id, status="READY")
        shipment.id = uuid4()
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, shipment]),
            add=Mock(),
            commit=AsyncMock(),
        )
        command_id = uuid4()
        authorization_id = uuid4()
        requested_by = uuid4()
        now = datetime.now(UTC)

        response = await commit_status_transition(
            db,
            order_id=order_id,
            command_id=command_id,
            authorization_id=authorization_id,
            requested_by=requested_by,
            authorization_expires_at=now + timedelta(seconds=10),
            payload=ShipmentStatusUpdateRequest(
                status="SHIPPED", carrier="Post", tracking_number="TRK-1"
            ),
            now=now,
        )

        assert response.status == "SHIPPED"
        assert shipment.status == "SHIPPED"
        transition = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], ShipmentTransition)
        )
        outbox = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], OutboxMessage)
        )
        assert outbox.event_id == transition.event_id
        assert outbox.payload["authorization_id"] == str(authorization_id)
        assert outbox.payload["command_id"] == str(command_id)
        db.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_recovery_reports_only_a_durable_transition() -> None:
    async def exercise() -> None:
        command_id = uuid4()
        empty_db = SimpleNamespace(scalar=AsyncMock(return_value=None))
        empty_recovery = await load_command_recovery(empty_db, command_id=command_id)
        assert empty_recovery.state == "NOT_COMMITTED"

        transition = ShipmentTransition(
            shipment_id=uuid4(),
            order_id=uuid4(),
            authorization_id=uuid4(),
            command_id=command_id,
            event_id=uuid4(),
            requested_by=uuid4(),
            from_status="READY",
            target_status="PROCESSING",
            carrier=None,
            tracking_number=None,
            occurred_at=datetime.now(UTC),
        )
        committed_db = SimpleNamespace(scalar=AsyncMock(return_value=transition))
        recovery = await load_command_recovery(committed_db, command_id=command_id)
        assert recovery.state == "COMMITTED"
        assert recovery.event_id == transition.event_id

    asyncio.run(exercise())
