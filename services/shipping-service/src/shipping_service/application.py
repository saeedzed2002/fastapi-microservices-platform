from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shipping_service.models import InboxMessage, OutboxMessage, Shipment, ShipmentTransition
from shipping_service.schemas import (
    OrderConfirmedPayload,
    ShipmentStatus,
    ShipmentStatusResponse,
    ShipmentStatusUpdateRequest,
    ShippingCommandRecoveryResponse,
)

_ORDER_CONFIRMED_EVENT = "order.confirmed.v1"
_SHIPPING_STATUS_UPDATED_EVENT = "shipping.status_updated.v1"

_ALLOWED_TRANSITIONS = {
    ("READY", "PROCESSING"),
    ("READY", "SHIPPED"),
    ("PROCESSING", "SHIPPED"),
    ("SHIPPED", "DELIVERED"),
}


async def process_order_event(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    event_type = str(envelope["event_type"])
    if await db.scalar(select(InboxMessage.id).where(InboxMessage.event_id == event_id)):
        return False

    db.add(InboxMessage(event_id=event_id, event_type=event_type))
    if event_type == _ORDER_CONFIRMED_EVENT:
        payload = OrderConfirmedPayload.model_validate(envelope["payload"])
        await db.execute(
            insert(Shipment)
            .values(order_id=payload.order_id, status="READY")
            .on_conflict_do_nothing(index_elements=[Shipment.order_id])
        )
    await db.commit()
    return True


def _event_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_transition(
    *, shipment: Shipment, payload: ShipmentStatusUpdateRequest
) -> tuple[str | None, str | None]:
    carrier = payload.carrier if payload.carrier is not None else shipment.carrier
    tracking_number = (
        payload.tracking_number if payload.tracking_number is not None else shipment.tracking_number
    )
    if (shipment.status, payload.status) not in _ALLOWED_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invalid shipment transition"
        )
    if payload.status == "SHIPPED" and (carrier is None or tracking_number is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="carrier and tracking number are required when shipping an order",
        )
    return carrier, tracking_number


def _response_for_transition(transition: ShipmentTransition) -> ShipmentStatusResponse:
    return ShipmentStatusResponse(
        order_id=transition.order_id,
        status=cast(ShipmentStatus, transition.target_status),
        carrier=transition.carrier,
        tracking_number=transition.tracking_number,
        command_id=transition.command_id,
        occurred_at=transition.occurred_at,
    )


def _matches_existing_transition(
    *,
    transition: ShipmentTransition,
    order_id: UUID,
    requested_by: UUID,
    payload: ShipmentStatusUpdateRequest,
) -> bool:
    return (
        transition.order_id == order_id
        and transition.requested_by == requested_by
        and transition.target_status == payload.status
        and (payload.carrier is None or transition.carrier == payload.carrier)
        and (
            payload.tracking_number is None or transition.tracking_number == payload.tracking_number
        )
    )


async def load_idempotent_status_transition(
    db: AsyncSession,
    *,
    order_id: UUID,
    command_id: UUID,
    requested_by: UUID,
    payload: ShipmentStatusUpdateRequest,
) -> ShipmentStatusResponse | None:
    transition = await db.scalar(
        select(ShipmentTransition).where(ShipmentTransition.command_id == command_id)
    )
    if transition is None:
        return None
    if _matches_existing_transition(
        transition=transition,
        order_id=order_id,
        requested_by=requested_by,
        payload=payload,
    ):
        return _response_for_transition(transition)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict")


async def commit_status_transition(
    db: AsyncSession,
    *,
    order_id: UUID,
    command_id: UUID,
    authorization_id: UUID,
    requested_by: UUID,
    authorization_expires_at: datetime,
    payload: ShipmentStatusUpdateRequest,
    now: datetime | None = None,
) -> ShipmentStatusResponse:
    current_time = now or datetime.now(UTC)
    if authorization_expires_at.tzinfo is None or authorization_expires_at <= current_time:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="fulfillment authorization expired"
        )
    existing = await db.scalar(
        select(ShipmentTransition)
        .where(ShipmentTransition.command_id == command_id)
        .with_for_update()
    )
    if existing is not None:
        await db.commit()
        if _matches_existing_transition(
            transition=existing,
            order_id=order_id,
            requested_by=requested_by,
            payload=payload,
        ):
            return _response_for_transition(existing)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict")
    shipment = await db.scalar(
        select(Shipment).where(Shipment.order_id == order_id).with_for_update()
    )
    if shipment is None:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="shipment not found")
    carrier, tracking_number = _validate_transition(shipment=shipment, payload=payload)
    occurred_at = current_time.astimezone(UTC)
    transition = ShipmentTransition(
        shipment_id=shipment.id,
        order_id=shipment.order_id,
        authorization_id=authorization_id,
        command_id=command_id,
        event_id=uuid4(),
        requested_by=requested_by,
        from_status=shipment.status,
        target_status=payload.status,
        carrier=carrier,
        tracking_number=tracking_number,
        occurred_at=occurred_at,
    )
    shipment.status = payload.status
    shipment.carrier = carrier
    shipment.tracking_number = tracking_number
    db.add(transition)
    db.add(
        OutboxMessage(
            event_id=transition.event_id,
            event_type=_SHIPPING_STATUS_UPDATED_EVENT,
            aggregate_type="shipment",
            aggregate_id=shipment.id,
            payload={
                "order_id": str(shipment.order_id),
                "authorization_id": str(authorization_id),
                "command_id": str(command_id),
                "requested_by": str(requested_by),
                "status": payload.status,
                "carrier": carrier,
                "tracking_number": tracking_number,
                "occurred_at": _event_timestamp(occurred_at),
            },
            correlation_id=shipment.order_id,
            causation_id=None,
            trace_id=uuid4().hex,
            occurred_at=occurred_at,
        )
    )
    await db.commit()
    return _response_for_transition(transition)


async def load_command_recovery(
    db: AsyncSession, *, command_id: UUID
) -> ShippingCommandRecoveryResponse:
    transition = await db.scalar(
        select(ShipmentTransition).where(ShipmentTransition.command_id == command_id)
    )
    if transition is None:
        return ShippingCommandRecoveryResponse(command_id=command_id, state="NOT_COMMITTED")
    return ShippingCommandRecoveryResponse(
        command_id=command_id,
        state="COMMITTED",
        order_id=transition.order_id,
        authorization_id=transition.authorization_id,
        event_id=transition.event_id,
        requested_by=transition.requested_by,
        status=cast(ShipmentStatus, transition.target_status),
        carrier=transition.carrier,
        tracking_number=transition.tracking_number,
        occurred_at=transition.occurred_at,
    )
