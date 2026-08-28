# mypy: disable-error-code=untyped-decorator

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from notification_service.config import get_settings
from notification_service.db import dispose_engine, get_session_factory
from notification_service.identity_gateway import IdentityOtpGateway
from notification_service.models import SmsOtpDelivery
from notification_service.providers import SmsIrBulkProvider
from notification_service.workers.celery_app import celery_app


class SmsDeliveryInProgress(Exception):
    pass


async def send_otp_sms(*, delivery_id: UUID) -> None:
    async with get_session_factory()() as db:
        delivery = await db.scalar(
            select(SmsOtpDelivery).where(SmsOtpDelivery.id == delivery_id).with_for_update()
        )
        if delivery is None or delivery.status == "SENT":
            return
        now = datetime.now(UTC)
        if (
            delivery.status == "SENDING"
            and delivery.processing_started_at is not None
            and (now - delivery.processing_started_at).total_seconds()
            < get_settings().sms_processing_lease_seconds
        ):
            raise SmsDeliveryInProgress("SMS delivery lease is still active")
        delivery.status = "SENDING"
        delivery.processing_started_at = now
        delivery.failure_reason = None
        await db.commit()
        phone = delivery.phone
    try:
        delivery_phone, otp_code = await IdentityOtpGateway(get_settings()).get_delivery_code(
            delivery_id
        )
        if delivery_phone != phone:
            raise ValueError("OTP delivery recipient mismatch")
        receipt = await asyncio.to_thread(
            SmsIrBulkProvider(get_settings()).send_otp,
            phone=phone,
            code=otp_code,
        )
    except Exception:
        async with get_session_factory()() as db:
            delivery = await db.get(SmsOtpDelivery, delivery_id)
            if delivery is not None and delivery.status != "SENT":
                delivery.status = "FAILED"
                delivery.processing_started_at = None
                delivery.failure_reason = "SMS provider delivery failed"
                await db.commit()
        raise
    async with get_session_factory()() as db:
        delivery = await db.get(SmsOtpDelivery, delivery_id)
        if delivery is None or delivery.status == "SENT":
            return
        delivery.status = "SENT"
        delivery.processing_started_at = None
        delivery.provider_message_id = receipt.provider_message_id
        delivery.sent_at = datetime.now(UTC)
        await db.commit()


async def _send_and_dispose(delivery_id: str) -> None:
    try:
        await send_otp_sms(delivery_id=UUID(delivery_id))
    finally:
        await dispose_engine()


@celery_app.task(
    name="notification_service.send_otp_sms",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_otp_sms_task(self: object, *, delivery_id: str) -> None:
    asyncio.run(_send_and_dispose(delivery_id))
