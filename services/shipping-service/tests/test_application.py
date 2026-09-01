import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from shipping_service.application import process_order_event


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
