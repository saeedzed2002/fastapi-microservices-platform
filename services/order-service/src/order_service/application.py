import asyncio
from collections.abc import Iterable
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from order_service.models import InboxMessage, Order, OrderItem, OrderStateTransition, OutboxMessage
from order_service.schemas import OrderItemResponse, OrderResponse

_TRANSITIONS = {
    ("PENDING", "inventory.reserved.v1"): "INVENTORY_RESERVED",
    ("PENDING", "inventory.reservation_failed.v1"): "CANCELLED",
    ("INVENTORY_RESERVED", "payment.processing.v1"): "PAYMENT_PENDING",
    ("PAYMENT_PENDING", "payment.succeeded.v1"): "CONFIRMED",
    ("PAYMENT_PENDING", "payment.failed.v1"): "CANCELLED",
}


def tracking_code() -> str:
    return f"ORD-{uuid4().hex[:16].upper()}"


async def order_response(db: AsyncSession, order: Order) -> OrderResponse:
    items = await db.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
    )
    return OrderResponse(
        id=order.id,
        status=order.status,
        tracking_code=order.tracking_code,
        currency=order.currency,
        total_amount=order.total_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[OrderItemResponse.model_validate(item) for item in items],
    )


async def load_owned_order_or_404(db: AsyncSession, order_id: UUID, customer_id: UUID) -> Order:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return order


def transition_order(
    order: Order,
    *,
    event_type: str,
    event_id: UUID,
    reason: str,
) -> bool:
    target = _TRANSITIONS.get((order.status, event_type))
    if target is None:
        return False
    order.status = target
    return True


def add_transition(
    db: AsyncSession,
    *,
    order: Order,
    previous: str | None,
    target: str,
    event_id: UUID | None,
    reason: str,
) -> None:
    db.add(
        OrderStateTransition(
            order_id=order.id,
            from_status=previous,
            to_status=target,
            event_id=event_id,
            reason=reason,
        )
    )


def add_outbox(
    db: AsyncSession,
    *,
    event_type: str,
    order_id: UUID,
    payload: dict[str, object],
    causation_id: UUID | None,
) -> None:
    db.add(
        OutboxMessage(
            event_type=event_type,
            aggregate_type="order",
            aggregate_id=order_id,
            payload=payload,
            correlation_id=order_id,
            causation_id=causation_id,
            trace_id=uuid4().hex,
        )
    )


def checkout_total(items: Iterable[tuple[Decimal, int]]) -> Decimal:
    return sum((amount * quantity for amount, quantity in items), Decimal("0"))


async def collect_checkout_snapshot(
    *,
    catalog_base_url: str,
    customer_base_url: str,
    access_token: str,
    address_id: UUID,
    item_quantities: dict[UUID, int],
) -> tuple[dict[str, str], list[dict[str, object]], str, Decimal]:
    headers = {"Authorization": f"Bearer {access_token}"}
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        variants_response, addresses_response = await asyncio.gather(
            client.post(
                f"{catalog_base_url}/api/v1/catalog/checkout/variants",
                headers=headers,
                json={"variant_ids": [str(variant_id) for variant_id in item_quantities]},
            ),
            client.get(f"{customer_base_url}/api/v1/customers/me/addresses", headers=headers),
        )
    if variants_response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="checkout variants unavailable"
        )
    if addresses_response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="checkout address unavailable"
        )
    address = next(
        (row for row in addresses_response.json() if row.get("id") == str(address_id)),
        None,
    )
    if address is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="checkout address not found"
        )
    rows = variants_response.json()
    currencies = {str(row["currency"]) for row in rows}
    if len(currencies) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="checkout currency mismatch"
        )
    snapshots: list[dict[str, object]] = [
        {
            "variant_id": UUID(str(row["variant_id"])),
            "sku": str(row["sku"]),
            "product_name": str(row["product_name"]),
            "unit_amount": Decimal(str(row["unit_amount"])),
            "quantity": item_quantities[UUID(str(row["variant_id"]))],
            "attributes": dict(row["attributes"]),
        }
        for row in rows
    ]
    return (
        {
            key: str(address[key])
            for key in ("recipient_name", "line1", "line2", "city", "postal_code", "country_code")
            if address.get(key) is not None
        },
        snapshots,
        currencies.pop(),
        checkout_total(
            (
                Decimal(str(row["unit_amount"])),
                cast(int, row["quantity"]),
            )
            for row in snapshots
        ),
    )


async def create_order(
    db: AsyncSession,
    *,
    customer_id: UUID,
    idempotency_key: str,
    delivery_address: dict[str, str],
    snapshots: list[dict[str, object]],
    currency: str,
    total_amount: Decimal,
    payment_method: str,
) -> Order:
    existing = await db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict"
            )
        return existing
    order = Order(
        customer_id=customer_id,
        tracking_code=tracking_code(),
        currency=currency,
        total_amount=total_amount,
        delivery_address=delivery_address,
        payment_method=payment_method,
        idempotency_key=idempotency_key,
    )
    db.add(order)
    await db.flush()
    for snapshot in snapshots:
        db.add(OrderItem(order_id=order.id, **snapshot))
    add_transition(
        db, order=order, previous=None, target="PENDING", event_id=None, reason="checkout accepted"
    )
    add_outbox(
        db,
        event_type="order.created.v1",
        order_id=order.id,
        payload={
            "order_id": str(order.id),
            "customer_id": str(customer_id),
            "currency": currency,
            "total_amount": str(total_amount),
            "payment_method": payment_method,
            "items": [
                {
                    "variant_id": str(snapshot["variant_id"]),
                    "sku": snapshot["sku"],
                    "quantity": snapshot["quantity"],
                }
                for snapshot in snapshots
            ],
        },
        causation_id=None,
    )
    await db.commit()
    await db.refresh(order)
    return order


async def process_saga_result(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    if await db.scalar(select(InboxMessage).where(InboxMessage.event_id == event_id)):
        return False
    payload = cast(dict[str, object], envelope["payload"])
    order = await db.scalar(
        select(Order).where(Order.id == UUID(str(payload["order_id"]))).with_for_update()
    )
    db.add(InboxMessage(event_id=event_id, event_type=str(envelope["event_type"])))
    if order is None:
        await db.commit()
        return False
    previous = order.status
    if not transition_order(
        order, event_type=str(envelope["event_type"]), event_id=event_id, reason="Kafka Saga event"
    ):
        await db.commit()
        return False
    add_transition(
        db,
        order=order,
        previous=previous,
        target=order.status,
        event_id=event_id,
        reason="Kafka Saga event",
    )
    if order.status == "CONFIRMED":
        add_outbox(
            db,
            event_type="order.confirmed.v1",
            order_id=order.id,
            payload={"order_id": str(order.id)},
            causation_id=event_id,
        )
    await db.commit()
    return True
