from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shipping_service.models import InboxMessage, Shipment
from shipping_service.schemas import OrderConfirmedPayload

_ORDER_CONFIRMED_EVENT = "order.confirmed.v1"


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
