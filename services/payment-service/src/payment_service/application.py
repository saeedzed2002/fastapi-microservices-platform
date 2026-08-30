from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.models import (
    InboxMessage,
    OutboxMessage,
    PaymentAttempt,
    PaymentIntent,
    PaymentReversal,
)
from payment_service.zarinpal import (
    ZarinpalClient,
    ZarinpalRejected,
    ZarinpalReverseResult,
    ZarinpalVerificationResult,
)


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


class PaymentReversalInProgress(PaymentWorkflowError):
    pass


class PaymentReversalRejected(PaymentWorkflowError):
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


@dataclass(frozen=True)
class ZarinpalReverse:
    order_id: UUID
    payment_status: str
    provider_reference: str
    reversal_id: UUID


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
            select(PaymentIntent)
            .where(PaymentIntent.id == intent_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ),
    )


async def _load_attempt_for_update(db: AsyncSession, attempt_id: UUID) -> PaymentAttempt | None:
    return cast(
        PaymentAttempt | None,
        await db.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.id == attempt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ),
    )


async def _load_reversal_for_update(db: AsyncSession, reversal_id: UUID) -> PaymentReversal | None:
    return cast(
        PaymentReversal | None,
        await db.scalar(
            select(PaymentReversal)
            .where(PaymentReversal.id == reversal_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
    # Check local provider configuration before writing a REQUESTING attempt.
    # A missing merchant ID cannot have reached Zarinpal, so it must not alter
    # the persisted payment state or block a later properly configured request.
    provider.ensure_configured()
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
    if intent.status in {"AWAITING_CUSTOMER", "REQUESTING"}:
        authority = await _recover_requesting_authority(db, intent)
        if authority is not None:
            return intent, authority
    if intent.status in {"REQUESTING", "VERIFYING"}:
        await db.commit()
        raise PaymentRequestInProgress
    if intent.status == "EXPIRED":
        await db.commit()
        raise PaymentExpired
    if intent.status != "AWAITING_CUSTOMER":
        await db.commit()
        raise PaymentNotReady
    intent.status = "REQUESTING"
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


async def _recover_requesting_authority(db: AsyncSession, intent: PaymentIntent) -> str | None:
    """Return a durable provider authority left before a local state transition.

    An authority is enough to resume the browser redirect without making another
    provider request. A request without an authority has an unknown provider
    outcome, so it remains in progress instead of risking a duplicate charge.
    """
    attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.intent_id == intent.id, PaymentAttempt.status == "REQUESTING")
        .order_by(PaymentAttempt.created_at.desc())
        .with_for_update()
        .limit(1)
    )
    if attempt is None:
        return None
    if attempt.authority is None:
        intent.status = "REQUESTING"
        await db.commit()
        return None

    attempt.status = "PENDING_CUSTOMER"
    intent.status = "PENDING_CUSTOMER"
    intent.provider_reference = f"zarinpal:{attempt.authority}"
    await db.commit()
    return attempt.authority


async def _record_zarinpal_rejection(
    db: AsyncSession, intent_id: UUID, attempt_id: UUID, code: str
) -> None:
    intent = await _load_intent_for_update(db, intent_id)
    attempt = await _load_attempt_for_update(db, attempt_id)
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
    attempt = await _load_attempt_for_update(db, attempt_id)
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
    attempt = await _load_attempt_for_update(db, attempt_id)
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
    if intent.status == "VERIFYING" or attempt.status == "VERIFYING":
        await db.commit()
        raise PaymentRequestInProgress
    if intent.status == "PENDING_CUSTOMER" and attempt.status == "PENDING_CUSTOMER":
        attempt.status = "CANCELLED"
        intent.status = "AWAITING_CUSTOMER"
        await db.commit()
        return ZarinpalCallback(intent.order_id, "cancelled", None)
    if intent.status == "AWAITING_CUSTOMER" and attempt.status == "CANCELLED":
        await db.commit()
        return ZarinpalCallback(intent.order_id, "cancelled", None)
    await db.commit()
    raise PaymentNotReady


async def _prepare_zarinpal_verification(
    db: AsyncSession, attempt_id: UUID
) -> tuple[PaymentIntent, bool]:
    attempt = await _load_attempt_for_update(db, attempt_id)
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
    attempt = await _load_attempt_for_update(db, attempt_id)
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


async def reverse_zarinpal_payment(
    db: AsyncSession,
    *,
    order_id: UUID,
    requested_by: UUID,
    idempotency_key: str,
    refund_request_id: UUID,
    provider: ZarinpalClient,
) -> ZarinpalReverse:
    """Persist a reversal intent before contacting Zarinpal.

    A provider response can be lost after it has acted. Keeping a durable
    ``REQUESTING`` record prevents a second reverse request from turning an
    uncertain external result into an unsafe duplicate operation.
    """
    provider.ensure_configured()
    prepared = await _prepare_zarinpal_reversal(
        db,
        order_id=order_id,
        requested_by=requested_by,
        idempotency_key=idempotency_key,
        refund_request_id=refund_request_id,
    )
    if isinstance(prepared, ZarinpalReverse):
        return prepared
    intent, attempt, reversal = prepared
    if attempt.authority is None:
        raise PaymentNotReady
    try:
        result = await provider.reverse_payment(authority=attempt.authority)
    except ZarinpalRejected as exc:
        await _record_zarinpal_reversal_rejection(db, reversal.id, exc.code)
        raise PaymentReversalRejected from exc
    return await _record_zarinpal_reversal(
        db,
        intent_id=intent.id,
        reversal_id=reversal.id,
        result=result,
    )


async def _prepare_zarinpal_reversal(
    db: AsyncSession,
    *,
    order_id: UUID,
    requested_by: UUID,
    idempotency_key: str,
    refund_request_id: UUID,
) -> tuple[PaymentIntent, PaymentAttempt, PaymentReversal] | ZarinpalReverse:
    intent = cast(
        PaymentIntent | None,
        await db.scalar(
            select(PaymentIntent).where(PaymentIntent.order_id == order_id).with_for_update()
        ),
    )
    if intent is None:
        raise PaymentIntentNotFound
    reversal = await db.scalar(
        select(PaymentReversal)
        .where(PaymentReversal.refund_request_id == refund_request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if reversal is not None:
        if reversal.idempotency_key != idempotency_key:
            await db.commit()
            if reversal.status == "SUCCEEDED":
                return ZarinpalReverse(
                    order_id=order_id,
                    payment_status="refunded",
                    provider_reference=intent.provider_reference,
                    reversal_id=reversal.id,
                )
            if reversal.status == "REQUESTING":
                raise PaymentReversalInProgress
            raise PaymentReversalRejected
        await db.commit()
        if reversal.status == "SUCCEEDED":
            return ZarinpalReverse(
                order_id=order_id,
                payment_status="refunded",
                provider_reference=intent.provider_reference,
                reversal_id=reversal.id,
            )
        if reversal.status == "REQUESTING":
            raise PaymentReversalInProgress
        raise PaymentReversalRejected
    if intent.method != "zarinpal" or intent.status != "SUCCEEDED":
        await db.commit()
        raise PaymentNotReady
    attempt = await db.scalar(
        select(PaymentAttempt)
        .where(
            PaymentAttempt.intent_id == intent.id,
            PaymentAttempt.provider == "zarinpal",
            PaymentAttempt.status == "SUCCEEDED",
        )
        .order_by(PaymentAttempt.created_at.desc())
        .with_for_update()
        .limit(1)
    )
    if attempt is None or attempt.authority is None:
        await db.commit()
        raise PaymentNotReady
    reversal = PaymentReversal(
        intent_id=intent.id,
        attempt_id=attempt.id,
        refund_request_id=refund_request_id,
        status="REQUESTING",
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        provider_code=None,
    )
    db.add(reversal)
    await db.commit()
    return intent, attempt, reversal


async def _record_zarinpal_reversal_rejection(
    db: AsyncSession, reversal_id: UUID, code: str
) -> None:
    reversal = await _load_reversal_for_update(db, reversal_id)
    intent = await _load_intent_for_update(db, reversal.intent_id) if reversal is not None else None
    if reversal is not None and intent is not None and reversal.status == "REQUESTING":
        reversal.status = "REJECTED"
        reversal.provider_code = code
        _add_outbox(
            db,
            intent=intent,
            event_type="payment.refund_failed.v1",
            payload={
                "order_id": str(intent.order_id),
                "provider_reference": intent.provider_reference,
                "refund_request_id": str(reversal.refund_request_id),
                "failure_code": code,
            },
            causation_id=None,
            trace_id=uuid4().hex,
        )
    await db.commit()


async def _record_zarinpal_reversal(
    db: AsyncSession,
    *,
    intent_id: UUID,
    reversal_id: UUID,
    result: ZarinpalReverseResult,
) -> ZarinpalReverse:
    intent = await _load_intent_for_update(db, intent_id)
    reversal = await _load_reversal_for_update(db, reversal_id)
    if intent is None or reversal is None:
        raise PaymentNotReady
    if reversal.status == "SUCCEEDED" and intent.status == "REFUNDED":
        await db.commit()
        return ZarinpalReverse(
            order_id=intent.order_id,
            payment_status="refunded",
            provider_reference=intent.provider_reference,
            reversal_id=reversal.id,
        )
    if reversal.status != "REQUESTING" or intent.status != "SUCCEEDED":
        await db.commit()
        raise PaymentNotReady
    reversal.status = "SUCCEEDED"
    reversal.provider_code = result.code
    intent.status = "REFUNDED"
    _add_outbox(
        db,
        intent=intent,
        event_type="payment.refunded.v1",
        payload={
            "order_id": str(intent.order_id),
            "provider_reference": intent.provider_reference,
            "reversal_id": str(reversal.id),
            "refund_request_id": str(reversal.refund_request_id),
        },
        causation_id=None,
        trace_id=uuid4().hex,
    )
    await db.commit()
    return ZarinpalReverse(
        order_id=intent.order_id,
        payment_status="refunded",
        provider_reference=intent.provider_reference,
        reversal_id=reversal.id,
    )


async def process_zarinpal_refund_request(
    db: AsyncSession,
    envelope: dict[str, object],
    *,
    provider: ZarinpalClient,
) -> bool:
    """Handle the durable Order refund command without a cross-service transaction."""
    event_id = UUID(str(envelope["event_id"]))
    if await db.scalar(select(InboxMessage).where(InboxMessage.event_id == event_id)):
        return False
    if str(envelope["event_type"]) != "order.refund_requested.v1":
        return False
    payload = cast(dict[str, object], envelope["payload"])
    order_id = UUID(str(payload["order_id"]))
    refund_request_id = UUID(str(payload["refund_request_id"]))
    requested_by = UUID(str(payload["requested_by"]))
    try:
        await reverse_zarinpal_payment(
            db,
            order_id=order_id,
            requested_by=requested_by,
            idempotency_key=f"refund-request:{refund_request_id}",
            refund_request_id=refund_request_id,
            provider=provider,
        )
    except PaymentNotReady:
        await _record_refund_not_ready(
            db,
            order_id=order_id,
            refund_request_id=refund_request_id,
        )
    except PaymentReversalRejected:
        # The rejection and compensating domain event are already durable.
        pass
    except PaymentReversalInProgress:
        # A provider result was not recorded. Do not send a second reverse
        # request; the operator must reconcile the persisted attempt.
        raise
    except PaymentIntentNotFound:
        raise
    db.add(InboxMessage(event_id=event_id, event_type="order.refund_requested.v1"))
    await db.commit()
    return True


async def _record_refund_not_ready(
    db: AsyncSession,
    *,
    order_id: UUID,
    refund_request_id: UUID,
) -> None:
    intent = await db.scalar(
        select(PaymentIntent).where(PaymentIntent.order_id == order_id).with_for_update()
    )
    if intent is None:
        raise PaymentIntentNotFound
    _add_outbox(
        db,
        intent=intent,
        event_type="payment.refund_failed.v1",
        payload={
            "order_id": str(order_id),
            "provider_reference": intent.provider_reference,
            "refund_request_id": str(refund_request_id),
            "failure_code": "payment_not_reversible",
        },
        causation_id=None,
        trace_id=uuid4().hex,
    )
    await db.commit()


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
