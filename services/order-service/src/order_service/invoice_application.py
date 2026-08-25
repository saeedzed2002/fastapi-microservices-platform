from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from order_service.models import InboxMessage, Invoice, Order, TaskIntent


async def accept_invoice_request(db: AsyncSession, envelope: dict[str, object]) -> bool:
    event_id = UUID(str(envelope["event_id"]))
    if await db.scalar(select(InboxMessage).where(InboxMessage.event_id == event_id)):
        return False
    payload = cast(dict[str, object], envelope["payload"])
    order = await db.scalar(
        select(Order).where(Order.id == UUID(str(payload["order_id"]))).with_for_update()
    )
    db.add(InboxMessage(event_id=event_id, event_type="order.confirmed.v1"))
    if order is None or order.status != "CONFIRMED":
        await db.commit()
        return False
    invoice = await db.scalar(select(Invoice).where(Invoice.order_id == order.id).with_for_update())
    if invoice is None:
        invoice = Invoice(order_id=order.id)
        db.add(invoice)
        await db.flush()
        db.add(
            TaskIntent(
                task_name="order.generate_invoice.v1",
                payload={
                    "invoice_id": str(invoice.id),
                    "order_id": str(order.id),
                    "causation_id": str(event_id),
                    "trace_id": str(envelope["trace_id"]),
                },
            )
        )
    await db.commit()
    return True
