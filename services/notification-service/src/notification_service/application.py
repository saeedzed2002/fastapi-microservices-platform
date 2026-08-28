from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.models import (
    InboxMessage,
    NotificationDelivery,
    SmsOtpDelivery,
    TaskIntent,
)


async def accept_invoice_generated(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    if await db.scalar(select(InboxMessage).where(InboxMessage.event_id == event_id)):
        return False
    payload = cast(dict[str, object], envelope["payload"])
    invoice_id = UUID(str(payload["invoice_id"]))
    recipient_email = str(payload.get("recipient_email") or "")
    db.add(InboxMessage(event_id=event_id, event_type="invoice.generated.v1"))
    delivery = await db.scalar(
        select(NotificationDelivery)
        .where(NotificationDelivery.invoice_id == invoice_id)
        .with_for_update()
    )
    if delivery is None and recipient_email:
        tracking_code = str(payload["tracking_code"])
        delivery = NotificationDelivery(
            invoice_id=invoice_id,
            recipient_email=recipient_email,
            subject=f"Invoice for order {tracking_code}",
            body=(
                f"Your invoice for order {tracking_code} has been generated. "
                f"Invoice reference: {invoice_id}."
            ),
        )
        db.add(delivery)
        await db.flush()
        db.add(
            TaskIntent(
                task_name="notification.send_invoice_email.v1",
                payload={"delivery_id": str(delivery.id), "causation_id": str(event_id)},
            )
        )
    await db.commit()
    return delivery is not None


async def accept_otp_sms_delivery(
    db: AsyncSession, *, delivery_id: UUID, phone: str
) -> SmsOtpDelivery:
    delivery = await db.get(SmsOtpDelivery, delivery_id, with_for_update=True)
    if delivery is not None:
        return delivery
    delivery = SmsOtpDelivery(id=delivery_id, phone=phone)
    db.add(delivery)
    await db.flush()
    db.add(
        TaskIntent(
            task_name="notification.send_otp_sms.v1",
            payload={"delivery_id": str(delivery.id)},
        )
    )
    await db.commit()
    return delivery
