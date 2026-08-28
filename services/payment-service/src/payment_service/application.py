from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.models import InboxMessage, OutboxMessage, PaymentAttempt, PaymentIntent
from payment_service.zarinpal import ZarinpalClient, ZarinpalRejected, ZarinpalVerificationResult


class PaymentWorkflowError(RuntimeError):
    pass


class PaymentIntentNotFound(PaymentWorkflowError):
    pass


class PaymentNotReady(PaymentWorkflowError):
    pass


class PaymentRequestInProgress(PaymentWorkflowError):
    pass


class PaymentExpired(PaymentWorkflowError):
    pass


class UnsupportedPaymentCurrency(PaymentWorkflowError):
    pass


@dataclass(frozen=True)
class ZarinpalStart:
    order_id: UUID
    authority: str
    redirect_url: str
    expires_at: datetime


@dataclass(frozen=True)
class ZarinpalCallback:
    order_id: UUID
    payment_status: str
    provider_reference: str | None


_PENDING_ZARINPAL_STATUSES = ("AWAITING_CUSTOMER", "REQUESTING", "PENDING_CUSTOMER", "VERIFYING")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _add_outbox(
    db: AsyncSession,
    *,
    intent: PaymentIntent,
    event_type: str,
    payload: dict[str, object],
    causation_id: UUID | None,
    trace_id: str,
) -> None:
    db.add(
        OutboxMessage(
            event_type=event_type,
            aggregate_type="payment_intent",
            aggregate_id=intent.id,
            payload=payload,
            correlation_id=intent.order_id,
            causation_id=causation_id,
            trace_id=trace_id,
        )
    )


async def _load_intent_for_update(db: AsyncSession, intent_id: UUID) -> PaymentIntent | None:
    return cast(
        PaymentIntent | None,
        await db.scalar(
            select(PaymentIntent).where(PaymentIntent.id == intent_id).with_for_update()
        ),
    )


async def process_reservation_event(
    db: AsyncSession,
    envelope: dict[str, object],
    *,
    reservation_minutes: int = 15,
) -> bool:
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
    is_zarinpal = method == "zarinpal"
    provider_reference = f"zarinpal-pending-{uuid4().hex}" if is_zarinpal else f"fake-{uuid4().hex}"
    intent = PaymentIntent(
        order_id=order_id,
        status="AWAITING_CUSTOMER" if is_zarinpal else "PROCESSING",
        currency=str(payload["currency"]),
        amount=Decimal(str(payload["total_amount"])),
        method=method,
        provider_reference=provider_reference,
        expires_at=utc_now() + timedelta(minutes=reservation_minutes) if is_zarinpal else None,
    )
    db.add(intent)
    await db.flush()
    _add_outbox(
        db,
        intent=intent,
        event_type="payment.processing.v1",
        payload={"order_id": str(order_id)},
        causation_id=event_id,
        trace_id=str(envelope["trace_id"]),
    )
    if is_zarinpal:
        await db.commit()
        return True

    outcome = "SUCCEEDED" if method == "test_success" else "FAILED"
    db.add(
        PaymentAttempt(
            intent_id=intent.id,
            provider="fake",
            status=outcome,
            provider_reference=provider_reference,
            authority=None,
            reference_id=None,
            failure_code=None,
        )
    )
    _add_outbox(
        db,
        intent=intent,
        event_type="payment.succeeded.v1" if outcome == "SUCCEEDED" else "payment.failed.v1",
        payload={"order_id": str(order_id), "provider_reference": provider_reference},
        causation_id=event_id,
        trace_id=str(envelope["trace_id"]),
    )
    intent.status = outcome
    await db.commit()
    return True


async def start_zarinpal_payment(
    db: AsyncSession,
    *,
    order_id: UUID,
    provider: ZarinpalClient,
    expected_currency: str,
) -> ZarinpalStart:
    intent, existing_authority = await _prepare_zarinpal_request(
        db, order_id=order_id, expected_currency=expected_currency
    )
    if existing_authority is not None:
        if intent.expires_at is None:
            raise PaymentNotReady
        return ZarinpalStart(
            order_id=intent.order_id,
            authority=existing_authority,
            redirect_url=provider.redirect_url(existing_authority),
            expires_at=intent.expires_at,
        )

    attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.intent_id == intent.id, PaymentAttempt.status == "REQUESTING")
        .order_by(PaymentAttempt.created_at.desc())
        .limit(1)
    )
    if attempt is None:
        raise PaymentNotReady
    try:
        request = await provider.create_payment(
            amount=int(intent.amount), description=f"Order {intent.order_id}"
        )
    except ZarinpalRejected as exc:
        await _record_zarinpal_rejection(db, intent.id, attempt.id, exc.code)
        raise
    return await _record_zarinpal_authority(
        db,
        intent_id=intent.id,
        attempt_id=attempt.id,
        authority=request.authority,
        redirect_url=request.redirect_url,
    )


async def _prepare_zarinpal_request(
    db: AsyncSession,
    *,
    order_id: UUID,
    expected_currency: str,
) -> tuple[PaymentIntent, str | None]:
    intent = await db.scalar(
        select(PaymentIntent).where(PaymentIntent.order_id == order_id).with_for_update()
    )
    if intent is None:
        raise PaymentIntentNotFound
    if intent.method != "zarinpal":
        raise PaymentNotReady
    if intent.currency.upper() != expected_currency.upper():
        raise UnsupportedPaymentCurrency
    if intent.amount <= 0 or intent.amount != intent.amount.to_integral_value():
        raise UnsupportedPaymentCurrency
    if intent.expires_at is None:
        raise PaymentNotReady
    if intent.expires_at <= utc_now():
        await _expire_intent(db, intent)
        await db.commit()
        raise PaymentExpired
    if intent.status == "PENDING_CUSTOMER":
        attempt = await db.scalar(
            select(PaymentAttempt)
            .where(
                PaymentAttempt.intent_id == intent.id,
                PaymentAttempt.status == "PENDING_CUSTOMER",
            )
            .order_by(PaymentAttempt.created_at.desc())
            .limit(1)
        )
        if attempt is None or attempt.authority is None:
            raise PaymentNotReady
        await db.commit()
        return intent, attempt.authority
    if intent.status in {"REQUESTING", "VERIFYING"}:
        await db.commit()
        raise PaymentRequestInProgress
    if intent.status == "EXPIRED":
        await db.commit()
        raise PaymentExpired
    if intent.status != "AWAITING_CUSTOMER":
        await db.commit()
        raise PaymentNotReady
    db.add(
        PaymentAttempt(
            intent_id=intent.id,
            provider="zarinpal",
            status="REQUESTING",
            provider_reference=f"zarinpal-request-{uuid4().hex}",
            authority=None,
            reference_id=None,
            failure_code=None,
        )
    )
    await db.commit()
    return intent, None


async def _record_zarinpal_rejection(
    db: AsyncSession, intent_id: UUID, attempt_id: UUID, code: str
) -> None:
    intent = await _load_intent_for_update(db, intent_id)
    attempt = await db.scalar(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt_id).with_for_update()
    )
    if intent is not None and attempt is not None and intent.status == "REQUESTING":
        attempt.status = "REJECTED"
        attempt.failure_code = code
        intent.status = "AWAITING_CUSTOMER"
    await db.commit()


async def _record_zarinpal_authority(
    db: AsyncSession,
    *,
    intent_id: UUID,
    attempt_id: UUID,
    authority: str,
    redirect_url: str,
) -> ZarinpalStart:
    intent = await _load_intent_for_update(db, intent_id)
    attempt = await db.scalar(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt_id).with_for_update()
    )
    if intent is None or attempt is None:
        raise PaymentNotReady
    attempt.authority = authority
    intent.provider_reference = f"zarinpal:{authority}"
    if intent.status == "EXPIRED":
        attempt.status = "EXPIRED"
        await db.commit()
        raise PaymentExpired
    if intent.status != "REQUESTING" or intent.expires_at is None:
        await db.commit()
        raise PaymentNotReady
    attempt.status = "PENDING_CUSTOMER"
    intent.status = "PENDING_CUSTOMER"
    await db.commit()
    return ZarinpalStart(
        order_id=intent.order_id,
        authority=authority,
        redirect_url=redirect_url,
        expires_at=intent.expires_at,
    )


async def handle_zarinpal_callback(
    db: AsyncSession,
    *,
    provider: ZarinpalClient,
    authority: str,
    provider_status: str,
) -> ZarinpalCallback:
    attempt = await db.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.provider == "zarinpal", PaymentAttempt.authority == authority
        )
    )
    if attempt is None:
        raise PaymentIntentNotFound
    if provider_status != "OK":
        return await _record_zarinpal_cancellation(db, attempt.id)
    intent, already_succeeded = await _prepare_zarinpal_verification(db, attempt.id)
    if already_succeeded:
        return ZarinpalCallback(intent.order_id, "succeeded", intent.provider_reference)
    verification = await provider.verify_payment(amount=int(intent.amount), authority=authority)
    return await _record_zarinpal_verification(db, attempt.id, verification)


async def _record_zarinpal_cancellation(db: AsyncSession, attempt_id: UUID) -> ZarinpalCallback:
    attempt = await db.scalar(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None:
        raise PaymentIntentNotFound
    intent = await _load_intent_for_update(db, attempt.intent_id)
    if intent is None:
        raise PaymentIntentNotFound
    if intent.status == "SUCCEEDED":
        await db.commit()
        return ZarinpalCallback(intent.order_id, "succeeded", intent.provider_reference)
    if intent.status == "EXPIRED":
        attempt.status = "EXPIRED"
        await db.commit()
        return ZarinpalCallback(intent.order_id, "expired", None)
    if attempt.status in {"PENDING_CUSTOMER", "VERIFYING", "REQUESTING"}:
        attempt.status = "CANCELLED"
        intent.status = "AWAITING_CUSTOMER"
    await db.commit()
    return ZarinpalCallback(intent.order_id, "cancelled", None)


async def _prepare_zarinpal_verification(
    db: AsyncSession, attempt_id: UUID
) -> tuple[PaymentIntent, bool]:
    attempt = await db.scalar(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None:
        raise PaymentIntentNotFound
    intent = await _load_intent_for_update(db, attempt.intent_id)
    if intent is None:
        raise PaymentIntentNotFound
    if intent.status == "SUCCEEDED":
        await db.commit()
        return intent, True
    if intent.status == "EXPIRED":
        await db.commit()
        return intent, False
    if attempt.status not in {"PENDING_CUSTOMER", "VERIFYING"}:
        await db.commit()
        raise PaymentNotReady
    attempt.status = "VERIFYING"
    intent.status = "VERIFYING"
    await db.commit()
    return intent, False


async def _record_zarinpal_verification(
    db: AsyncSession,
    attempt_id: UUID,
    verification: ZarinpalVerificationResult,
) -> ZarinpalCallback:
    attempt = await db.scalar(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None:
        raise PaymentIntentNotFound
    intent = await _load_intent_for_update(db, attempt.intent_id)
    if intent is None:
        raise PaymentIntentNotFound
    if intent.status == "SUCCEEDED":
        await db.commit()
        return ZarinpalCallback(intent.order_id, "succeeded", intent.provider_reference)
    if verification.succeeded:
        attempt.reference_id = verification.reference_id
        if intent.status == "EXPIRED":
            attempt.status = "LATE_SUCCESS"
            await db.commit()
            return ZarinpalCallback(intent.order_id, "expired", verification.reference_id)
        if intent.status != "VERIFYING":
            await db.commit()
            raise PaymentNotReady
        attempt.status = "SUCCEEDED"
        intent.status = "SUCCEEDED"
        intent.provider_reference = f"zarinpal:{verification.reference_id}"
        _add_outbox(
            db,
            intent=intent,
            event_type="payment.succeeded.v1",
            payload={
                "order_id": str(intent.order_id),
                "provider_reference": intent.provider_reference,
            },
            causation_id=None,
            trace_id=uuid4().hex,
        )
        await db.commit()
        return ZarinpalCallback(intent.order_id, "succeeded", intent.provider_reference)
    if intent.status == "EXPIRED":
        attempt.status = "EXPIRED"
        attempt.failure_code = verification.code
        await db.commit()
        return ZarinpalCallback(intent.order_id, "expired", None)
    if intent.status != "VERIFYING":
        await db.commit()
        raise PaymentNotReady
    attempt.status = "FAILED"
    attempt.failure_code = verification.code
    intent.status = "AWAITING_CUSTOMER"
    await db.commit()
    return ZarinpalCallback(intent.order_id, "failed", None)


async def expire_due_payment_intents(db: AsyncSession, *, now: datetime | None = None) -> int:
    due_at = now or utc_now()
    intents = list(
        await db.scalars(
            select(PaymentIntent)
            .where(
                PaymentIntent.method == "zarinpal",
                PaymentIntent.status.in_(_PENDING_ZARINPAL_STATUSES),
                PaymentIntent.expires_at.is_not(None),
                PaymentIntent.expires_at <= due_at,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for intent in intents:
        await _expire_intent(db, intent)
    if intents:
        await db.commit()
    return len(intents)


async def _expire_intent(db: AsyncSession, intent: PaymentIntent) -> None:
    if intent.status == "EXPIRED":
        return
    attempts = list(
        await db.scalars(
            select(PaymentAttempt).where(
                PaymentAttempt.intent_id == intent.id,
                PaymentAttempt.status.in_(("REQUESTING", "PENDING_CUSTOMER", "VERIFYING")),
            )
        )
    )
    for attempt in attempts:
        attempt.status = "EXPIRED"
    intent.status = "EXPIRED"
    _add_outbox(
        db,
        intent=intent,
        event_type="payment.failed.v1",
        payload={
            "order_id": str(intent.order_id),
            "provider_reference": f"zarinpal-expired:{intent.id}",
        },
        causation_id=None,
        trace_id=uuid4().hex,
    )
