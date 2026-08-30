import asyncio
import base64
import binascii
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from order_service.models import (
    InboxMessage,
    Invoice,
    Order,
    OrderFulfillment,
    OrderItem,
    OrderRefundRequest,
    OrderStateTransition,
    OutboxMessage,
)
from order_service.schemas import (
    AdminOrderPage,
    AdminOrderResponse,
    CustomerOrderPage,
    FulfillmentResponse,
    FulfillmentUpdateRequest,
    InvoiceSummaryResponse,
    OrderItemResponse,
    OrderResponse,
    OrderStateTransitionResponse,
    OrderStatus,
    OrderSummaryResponse,
    RefundRequestResponse,
)

_TRANSITIONS = {
    ("PENDING", "inventory.reserved.v1"): "INVENTORY_RESERVED",
    ("PENDING", "inventory.reservation_failed.v1"): "CANCELLED",
    ("INVENTORY_RESERVED", "payment.processing.v1"): "PAYMENT_PENDING",
    ("PAYMENT_PENDING", "payment.succeeded.v1"): "CONFIRMED",
    ("PAYMENT_PENDING", "payment.failed.v1"): "CANCELLED",
    ("REFUND_PENDING", "payment.refunded.v1"): "REFUNDED",
    ("REFUND_PENDING", "payment.refund_failed.v1"): "CONFIRMED",
}

_FULFILLMENT_TRANSITIONS = {
    ("CONFIRMED", "PROCESSING"),
    ("CONFIRMED", "SHIPPED"),
    ("PROCESSING", "SHIPPED"),
    ("SHIPPED", "DELIVERED"),
}


class InvalidOrderCursor(ValueError):
    pass


def tracking_code() -> str:
    return f"ORD-{uuid4().hex[:16].upper()}"


def validate_checkout_payment(*, payment_method: str, currency: str, total_amount: Decimal) -> None:
    if payment_method != "zarinpal":
        return
    if currency.upper() != "IRT":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="zarinpal requires IRT currency",
        )
    if total_amount <= 0 or total_amount != total_amount.to_integral_value():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="zarinpal amount must be a positive whole IRT value",
        )


async def order_response(db: AsyncSession, order: Order) -> OrderResponse:
    items = await db.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
    )
    fulfillment = await db.scalar(
        select(OrderFulfillment).where(OrderFulfillment.order_id == order.id)
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
        fulfillment=(
            FulfillmentResponse.model_validate(fulfillment) if fulfillment is not None else None
        ),
    )


def order_summary_response(order: Order) -> OrderSummaryResponse:
    return OrderSummaryResponse(
        id=order.id,
        status=cast(OrderStatus, order.status),
        tracking_code=order.tracking_code,
        currency=order.currency,
        total_amount=order.total_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


async def admin_order_response(db: AsyncSession, order: Order) -> AdminOrderResponse:
    response = await order_response(db, order)
    transitions = await db.scalars(
        select(OrderStateTransition)
        .where(OrderStateTransition.order_id == order.id)
        .order_by(OrderStateTransition.created_at, OrderStateTransition.id)
    )
    invoice = await db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    refund_request = await db.scalar(
        select(OrderRefundRequest).where(OrderRefundRequest.order_id == order.id)
    )
    return AdminOrderResponse(
        **response.model_dump(),
        customer_id=order.customer_id,
        customer_email=order.customer_email,
        delivery_address=order.delivery_address,
        payment_method=order.payment_method,
        transitions=[OrderStateTransitionResponse.model_validate(row) for row in transitions],
        invoice=(
            InvoiceSummaryResponse(status=invoice.status, generated_at=invoice.generated_at)
            if invoice is not None
            else None
        ),
        refund_request_id=refund_request.id if refund_request is not None else None,
    )


async def load_order_or_404(db: AsyncSession, order_id: UUID) -> Order:
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return order


async def load_owned_order_or_404(db: AsyncSession, order_id: UUID, customer_id: UUID) -> Order:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return order


async def update_order_fulfillment(
    db: AsyncSession,
    *,
    order_id: UUID,
    updated_by: UUID,
    payload: FulfillmentUpdateRequest,
) -> Order:
    order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    fulfillment = await db.scalar(
        select(OrderFulfillment).where(OrderFulfillment.order_id == order.id).with_for_update()
    )
    carrier = (
        payload.carrier
        if payload.carrier is not None
        else (fulfillment.carrier if fulfillment is not None else None)
    )
    tracking_number = (
        payload.tracking_number
        if payload.tracking_number is not None
        else (fulfillment.tracking_number if fulfillment is not None else None)
    )
    if payload.status == "SHIPPED" and (carrier is None or tracking_number is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="carrier and tracking number are required when shipping an order",
        )
    if (
        order.status != payload.status
        and (order.status, payload.status) not in _FULFILLMENT_TRANSITIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid fulfillment transition"
        )
    if fulfillment is None:
        fulfillment = OrderFulfillment(
            order_id=order.id,
            carrier=carrier,
            tracking_number=tracking_number,
            updated_by=updated_by,
        )
        db.add(fulfillment)
    else:
        fulfillment.carrier = carrier
        fulfillment.tracking_number = tracking_number
        fulfillment.updated_by = updated_by
    previous = order.status
    order.status = payload.status
    if previous != order.status:
        add_transition(
            db,
            order=order,
            previous=previous,
            target=order.status,
            event_id=None,
            reason="Administrator fulfillment update",
        )
    add_outbox(
        db,
        event_type="order.fulfillment_updated.v1",
        order_id=order.id,
        payload={"order_id": str(order.id), "status": order.status},
        causation_id=None,
    )
    await db.commit()
    return order


async def request_order_refund(
    db: AsyncSession,
    *,
    order_id: UUID,
    requested_by: UUID,
    idempotency_key: str,
) -> RefundRequestResponse:
    order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    refund_request = await db.scalar(
        select(OrderRefundRequest).where(OrderRefundRequest.order_id == order.id).with_for_update()
    )
    if refund_request is not None:
        await db.commit()
        if refund_request.idempotency_key != idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="refund request already exists"
            )
        return RefundRequestResponse(
            order_id=order.id,
            refund_request_id=refund_request.id,
            status="REFUND_PENDING",
        )
    key_owner = await db.scalar(
        select(OrderRefundRequest).where(OrderRefundRequest.idempotency_key == idempotency_key)
    )
    if key_owner is not None:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict")
    if order.status != "CONFIRMED" or order.payment_method != "zarinpal":
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="order is not refundable")
    refund_request = OrderRefundRequest(
        order_id=order.id,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
    )
    db.add(refund_request)
    previous = order.status
    order.status = "REFUND_PENDING"
    add_transition(
        db,
        order=order,
        previous=previous,
        target=order.status,
        event_id=None,
        reason="Administrator refund request",
    )
    try:
        await db.flush()
    except IntegrityError as exc:
        # Different orders can arrive concurrently with the same key. The
        # database constraint is authoritative; reload after rollback so a
        # same-order retry stays idempotent and a cross-order reuse is a 409.
        await db.rollback()
        key_owner = await db.scalar(
            select(OrderRefundRequest).where(OrderRefundRequest.idempotency_key == idempotency_key)
        )
        if key_owner is not None and key_owner.order_id == order_id:
            return RefundRequestResponse(
                order_id=order_id,
                refund_request_id=key_owner.id,
                status="REFUND_PENDING",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict"
        ) from exc
    add_outbox(
        db,
        event_type="order.refund_requested.v1",
        order_id=order.id,
        payload={
            "order_id": str(order.id),
            "refund_request_id": str(refund_request.id),
            "requested_by": str(requested_by),
        },
        causation_id=None,
    )
    await db.commit()
    return RefundRequestResponse(
        order_id=order.id,
        refund_request_id=refund_request.id,
        status="REFUND_PENDING",
    )


def encode_order_cursor(order: Order) -> str:
    payload = f"{order.created_at.astimezone(UTC).isoformat()}|{order.id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_order_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        raw_timestamp, raw_id = (
            base64.urlsafe_b64decode(padded_cursor).decode("utf-8").split("|", 1)
        )
        created_at = datetime.fromisoformat(raw_timestamp)
        order_id = UUID(raw_id)
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise InvalidOrderCursor from exc
    if created_at.tzinfo is None:
        raise InvalidOrderCursor
    return created_at.astimezone(UTC), order_id


async def list_customer_orders(
    *, db: AsyncSession, customer_id: UUID, limit: int, cursor: str | None
) -> CustomerOrderPage:
    rows = await _list_orders(
        db=db,
        filters=[Order.customer_id == customer_id],
        limit=limit,
        cursor=cursor,
    )
    return CustomerOrderPage(
        items=[order_summary_response(order) for order in rows[:limit]],
        next_cursor=encode_order_cursor(rows[limit - 1]) if len(rows) > limit else None,
    )


async def list_administrator_orders(
    *, db: AsyncSession, status_filter: OrderStatus | None, limit: int, cursor: str | None
) -> AdminOrderPage:
    filters = [Order.status == status_filter] if status_filter is not None else []
    rows = await _list_orders(db=db, filters=filters, limit=limit, cursor=cursor)
    return AdminOrderPage(
        items=[order_summary_response(order) for order in rows[:limit]],
        next_cursor=encode_order_cursor(rows[limit - 1]) if len(rows) > limit else None,
    )


async def _list_orders(
    *,
    db: AsyncSession,
    filters: list[ColumnElement[bool]],
    limit: int,
    cursor: str | None,
) -> list[Order]:
    conditions = list(filters)
    if cursor is not None:
        created_at, order_id = decode_order_cursor(cursor)
        conditions.append(
            or_(
                Order.created_at < created_at,
                and_(Order.created_at == created_at, Order.id < order_id),
            )
        )
    statement = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(limit + 1)
    if conditions:
        statement = statement.where(*conditions)
    rows = await db.scalars(statement)
    return list(rows)


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
) -> tuple[dict[str, str], str | None, list[dict[str, object]], str, Decimal]:
    headers = {"Authorization": f"Bearer {access_token}"}
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        variants_response, addresses_response, customer_response = await asyncio.gather(
            client.post(
                f"{catalog_base_url}/api/v1/catalog/checkout/variants",
                headers=headers,
                json={"variant_ids": [str(variant_id) for variant_id in item_quantities]},
            ),
            client.get(f"{customer_base_url}/api/v1/customers/me/addresses", headers=headers),
            client.get(f"{customer_base_url}/api/v1/customers/me", headers=headers),
        )
    if variants_response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="checkout variants unavailable"
        )
    if (
        addresses_response.status_code != status.HTTP_200_OK
        or customer_response.status_code != status.HTTP_200_OK
    ):
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
    customer_email = required_customer_email(customer_response.json())
    return (
        {
            key: str(address[key])
            for key in ("recipient_name", "line1", "line2", "city", "postal_code", "country_code")
            if address.get(key) is not None
        },
        customer_email,
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


def required_customer_email(customer: dict[str, object]) -> str:
    email = customer.get("email")
    if not isinstance(email, str) or not email.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="checkout email unavailable",
        )
    return email.strip()


async def create_order(
    db: AsyncSession,
    *,
    customer_id: UUID,
    idempotency_key: str,
    delivery_address: dict[str, str],
    customer_email: str | None,
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
        customer_email=customer_email,
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
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = cast(
            Order | None,
            await db.scalar(select(Order).where(Order.idempotency_key == idempotency_key)),
        )
        if existing is not None:
            if existing.customer_id != customer_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict"
                ) from exc
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="order could not be created"
        ) from exc
    await db.refresh(order)
    return order


async def load_idempotent_order(
    db: AsyncSession, *, customer_id: UUID, idempotency_key: str
) -> Order | None:
    existing = await db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
    if existing is not None and existing.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict")
    return existing


async def wait_for_payment_pending(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    order_id: UUID,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> OrderResponse | None:
    """Observe durable Saga state without holding a database transaction open."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        async with session_factory() as polling_db:
            order = await polling_db.get(Order, order_id)
            if order is None:
                raise RuntimeError("checkout order disappeared")
            if order.status in {"PAYMENT_PENDING", "CANCELLED"}:
                return await order_response(polling_db, order)
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(poll_interval_seconds, remaining))


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
    if str(envelope["event_type"]) == "payment.succeeded.v1" and order.status == "CONFIRMED":
        add_outbox(
            db,
            event_type="order.confirmed.v1",
            order_id=order.id,
            payload={"order_id": str(order.id)},
            causation_id=event_id,
        )
    await db.commit()
    return True
