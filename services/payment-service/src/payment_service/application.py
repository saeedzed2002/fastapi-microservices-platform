from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.models import InboxMessage, OutboxMessage, PaymentAttempt, PaymentIntent


async def process_reservation_event(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    if await db.scalar(select(InboxMessage).where(InboxMessage.event_id == event_id)):
        return False
    payload = cast(dict[str, object], envelope["payload"])
    order_id = UUID(str(payload["order_id"]))
    intent = await db.scalar(select(PaymentIntent).where(PaymentIntent.order_id == order_id))
    db.add(InboxMessage(event_id=event_id, event_type=str(envelope["event_type"])))
    if intent is not None:
        await db.commit()
        return False
    method = str(payload["payment_method"])
    provider_reference = f"fake-{uuid4().hex}"
    intent = PaymentIntent(
        order_id=order_id,
        status="PROCESSING",
        currency=str(payload["currency"]),
        amount=Decimal(str(payload["total_amount"])),
        method=method,
        provider_reference=provider_reference,
    )
    db.add(intent)
    await db.flush()
    outcome = "SUCCEEDED" if method == "test_success" else "FAILED"
    db.add(
        PaymentAttempt(intent_id=intent.id, status=outcome, provider_reference=provider_reference)
    )
    for event_type, event_payload in (
        ("payment.processing.v1", {"order_id": str(order_id)}),
        (
            "payment.succeeded.v1" if outcome == "SUCCEEDED" else "payment.failed.v1",
            {"order_id": str(order_id), "provider_reference": provider_reference},
        ),
    ):
        db.add(
            OutboxMessage(
                event_type=event_type,
                aggregate_type="payment_intent",
                aggregate_id=intent.id,
                payload=event_payload,
                correlation_id=order_id,
                causation_id=event_id,
                trace_id=str(envelope["trace_id"]),
            )
        )
    intent.status = outcome
    await db.commit()
    return True
