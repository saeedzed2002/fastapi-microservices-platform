import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select

from notification_service.config import Settings
from notification_service.db import get_session_factory
from notification_service.models import TaskIntent
from notification_service.workers.celery_app import celery_app


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _claim_intent(settings: Settings) -> TaskIntent | None:
    async with get_session_factory()() as db:
        stale_before = datetime.now(UTC) - timedelta(
            seconds=settings.task_dispatcher_claim_lease_seconds
        )
        intent = await db.scalar(
            select(TaskIntent)
            .where(
                or_(
                    TaskIntent.status == "PENDING",
                    (TaskIntent.status == "DISPATCHING")
                    & (TaskIntent.dispatch_claimed_at < stale_before),
                )
            )
            .order_by(TaskIntent.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if intent is None:
            return None
        intent.status = "DISPATCHING"
        intent.attempts += 1
        intent.dispatch_claimed_at = datetime.now(UTC)
        intent.dispatch_claim_token = uuid4()
        await db.commit()
        return intent


async def _mark(
    intent_id: UUID,
    *,
    claim_token: UUID | None,
    status: str,
    error: str | None = None,
) -> None:
    async with get_session_factory()() as db:
        intent = await db.get(TaskIntent, intent_id)
        if (
            intent is None
            or intent.status != "DISPATCHING"
            or intent.dispatch_claim_token != claim_token
        ):
            return
        intent.status = status
        intent.last_error = error[:2000] if error else None
        intent.dispatch_claimed_at = None
        intent.dispatch_claim_token = None
        intent.dispatched_at = datetime.now(UTC) if status == "DISPATCHED" else None
        await db.commit()


async def run_task_dispatcher(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        intent = await _claim_intent(settings)
        if intent is None:
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
            continue
        try:
            task_name, queue_name = {
                "notification.send_invoice_email.v1": (
                    "notification_service.send_invoice_email",
                    "notification.email",
                ),
                "notification.send_otp_sms.v1": (
                    "notification_service.send_otp_sms",
                    "notification.sms",
                ),
                "notification.send_password_reset_email.v1": (
                    "notification_service.send_password_reset_email",
                    "notification.email",
                ),
            }[intent.task_name]
            await asyncio.to_thread(
                celery_app.send_task,
                task_name,
                kwargs=intent.payload,
                queue=queue_name,
            )
            await _mark(
                intent.id,
                claim_token=intent.dispatch_claim_token,
                status="DISPATCHED",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await _mark(
                intent.id,
                claim_token=intent.dispatch_claim_token,
                status="PENDING",
                error=str(exc),
            )
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
