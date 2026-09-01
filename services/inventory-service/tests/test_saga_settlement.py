import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from inventory_service.application import process_saga_event
from inventory_service.models import StockMovement


def _event(
    event_type: str, order_id: object, payload: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "payload": {"order_id": str(order_id), **(payload or {})},
        "trace_id": uuid4().hex,
    }


def _movements(db: SimpleNamespace) -> list[StockMovement]:
    return [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], StockMovement)
    ]


def test_payment_success_commits_reserved_stock_once() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        stock = SimpleNamespace(id=uuid4(), sku="SKU-1", on_hand=10, reserved=2, version=4)
        reservation = SimpleNamespace(
            status="RESERVED",
            items=[{"sku": "SKU-1", "quantity": 2}],
            committed_at=None,
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, reservation, stock]),
            add=Mock(),
            commit=AsyncMock(),
        )

        assert await process_saga_event(db, _event("payment.succeeded.v1", order_id))
        assert (stock.on_hand, stock.reserved, stock.version) == (8, 0, 5)
        assert reservation.status == "COMMITTED"
        assert reservation.committed_at is not None
        movements = _movements(db)
        assert [
            (movement.kind, movement.quantity_delta, movement.reserved_delta)
            for movement in movements
        ] == [("commit", -2, -2)]

    asyncio.run(exercise())


def test_payment_refund_returns_committed_stock_once() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        stock = SimpleNamespace(id=uuid4(), sku="SKU-1", on_hand=8, reserved=0, version=5)
        reservation = SimpleNamespace(
            status="COMMITTED",
            items=[{"sku": "SKU-1", "quantity": 2}],
            returned_at=None,
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, reservation, stock]),
            add=Mock(),
            commit=AsyncMock(),
        )

        assert await process_saga_event(db, _event("payment.refunded.v1", order_id))
        assert (stock.on_hand, stock.reserved, stock.version) == (10, 0, 6)
        assert reservation.status == "RETURNED"
        assert reservation.returned_at is not None
        movements = _movements(db)
        assert [
            (movement.kind, movement.quantity_delta, movement.reserved_delta)
            for movement in movements
        ] == [("refund_return", 2, 0)]

    asyncio.run(exercise())


def test_refund_after_a_missed_success_releases_the_reservation() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        stock = SimpleNamespace(id=uuid4(), sku="SKU-1", on_hand=10, reserved=2, version=4)
        reservation = SimpleNamespace(
            status="RESERVED",
            items=[{"sku": "SKU-1", "quantity": 2}],
            released_at=None,
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, reservation, stock]),
            add=Mock(),
            commit=AsyncMock(),
        )

        assert await process_saga_event(db, _event("payment.refunded.v1", order_id))
        assert (stock.on_hand, stock.reserved, stock.version) == (10, 0, 5)
        assert reservation.status == "RELEASED"
        assert _movements(db)[0].kind == "release"

    asyncio.run(exercise())


def test_physical_return_receipt_restocks_committed_stock_once() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        return_request_id = uuid4()
        stock = SimpleNamespace(id=uuid4(), sku="SKU-1", on_hand=8, reserved=0, version=5)
        reservation = SimpleNamespace(
            status="COMMITTED",
            items=[{"sku": "SKU-1", "quantity": 2}],
            returned_at=None,
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, reservation, stock]),
            add=Mock(),
            commit=AsyncMock(),
        )

        assert await process_saga_event(
            db,
            _event(
                "order.return_received.v1",
                order_id,
                {
                    "return_request_id": str(return_request_id),
                    "items": [{"sku": "SKU-1", "quantity": 2}],
                },
            ),
        )
        assert (stock.on_hand, stock.reserved, stock.version) == (10, 0, 6)
        assert reservation.status == "RETURNED"
        assert reservation.returned_at is not None
        assert [movement.kind for movement in _movements(db)] == ["return_received"]
        assert _movements(db)[0].idempotency_key == f"return-received:{return_request_id}:SKU-1"

    asyncio.run(exercise())


def test_post_delivery_payment_refund_never_restocks_before_physical_receipt() -> None:
    async def exercise() -> None:
        order_id = uuid4()
        stock = SimpleNamespace(id=uuid4(), sku="SKU-1", on_hand=8, reserved=0, version=5)
        reservation = SimpleNamespace(
            status="COMMITTED",
            items=[{"sku": "SKU-1", "quantity": 2}],
            returned_at=None,
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[None, reservation]),
            add=Mock(),
            commit=AsyncMock(),
        )

        assert await process_saga_event(
            db,
            _event("payment.refunded.v1", order_id, {"return_request_id": str(uuid4())}),
        )
        assert (stock.on_hand, stock.reserved, stock.version) == (8, 0, 5)
        assert reservation.status == "COMMITTED"
        assert _movements(db) == []

    asyncio.run(exercise())
