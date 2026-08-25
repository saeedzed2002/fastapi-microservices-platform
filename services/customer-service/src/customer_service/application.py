from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.models import Customer, InboxMessage


async def provision_customer(db: AsyncSession, *, user_id: UUID, email: str) -> Customer:
    customer = await db.get(Customer, user_id)
    if customer is None:
        customer = Customer(id=user_id, email=email, display_name=email.split("@", 1)[0])
        db.add(customer)
    else:
        customer.email = email
    return customer


async def provision_identity_customer(
    db: AsyncSession, *, event_id: UUID, user_id: UUID, email: str
) -> Customer | None:
    duplicate = await db.scalar(select(InboxMessage.id).where(InboxMessage.event_id == event_id))
    if duplicate is not None:
        return None
    customer = await provision_customer(db, user_id=user_id, email=email)
    db.add(InboxMessage(event_id=event_id, event_type="identity.user_registered.v1"))
    return customer
