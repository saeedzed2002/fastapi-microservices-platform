# mypy: disable-error-code=untyped-decorator

import asyncio
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select

from notification_service.config import get_settings
from notification_service.db import dispose_engine, get_session_factory
from notification_service.models import NotificationDelivery
from notification_service.workers.celery_app import celery_app


class EmailDeliveryInProgress(Exception):
    pass


def _send_email(*, recipient: str, subject: str, body: str) -> str:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
    ) as smtp:
        smtp.send_message(message)
    return message["Message-ID"] or ""


async def send_invoice_email(*, delivery_id: UUID) -> None:
    async with get_session_factory()() as db:
        delivery = await db.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id)
            .with_for_update()
        )
        if delivery is None or delivery.status == "SENT":
            return
        now = datetime.now(UTC)
        if (
            delivery.status == "SENDING"
            and delivery.processing_started_at is not None
            and (now - delivery.processing_started_at).total_seconds()
            < get_settings().email_processing_lease_seconds
        ):
            raise EmailDeliveryInProgress("email delivery lease is still active")
        delivery.status = "SENDING"
        delivery.processing_started_at = now
        delivery.failure_reason = None
        await db.commit()
        recipient, subject, body = delivery.recipient_email, delivery.subject, delivery.body
    try:
        provider_message_id = await asyncio.to_thread(
            _send_email, recipient=recipient, subject=subject, body=body
        )
    except Exception as exc:
        async with get_session_factory()() as db:
            delivery = await db.get(NotificationDelivery, delivery_id)
            if delivery is not None and delivery.status != "SENT":
                delivery.status = "FAILED"
                delivery.processing_started_at = None
                delivery.failure_reason = str(exc)[:2000]
                await db.commit()
        raise
    async with get_session_factory()() as db:
        delivery = await db.get(NotificationDelivery, delivery_id)
        if delivery is None or delivery.status == "SENT":
            return
        delivery.status = "SENT"
        delivery.processing_started_at = None
        delivery.provider_message_id = provider_message_id
        delivery.sent_at = datetime.now(UTC)
        await db.commit()


async def _send_and_dispose(delivery_id: str) -> None:
    try:
        await send_invoice_email(delivery_id=UUID(delivery_id))
    finally:
        await dispose_engine()


@celery_app.task(
    name="notification_service.send_invoice_email",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 7},
)
def send_invoice_email_task(self: object, *, delivery_id: str, causation_id: str) -> None:
    del causation_id
    asyncio.run(_send_and_dispose(delivery_id))
