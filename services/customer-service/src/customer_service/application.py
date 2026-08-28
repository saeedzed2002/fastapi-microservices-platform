from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.models import Customer, InboxMessage


async def provision_customer(
    db: AsyncSession, *, user_id: UUID, email: str | None, phone: str | None = None
) -> Customer:
    customer = await db.get(Customer, user_id)
    if customer is None:
        display_name = email.split("@", 1)[0] if email else phone or "customer"
        customer = Customer(id=user_id, email=email, phone=phone, display_name=display_name)
        db.add(customer)
    else:
        customer.email = email
        customer.phone = phone
    return customer


async def provision_identity_customer(
    db: AsyncSession,
    *,
    event_id: UUID,
    event_type: str,
    user_id: UUID,
    email: str | None,
    phone: str | None,
) -> Customer | None:
    duplicate = await db.scalar(select(InboxMessage.id).where(InboxMessage.event_id == event_id))
    if duplicate is not None:
        return None
    customer = await provision_customer(db, user_id=user_id, email=email, phone=phone)
    db.add(InboxMessage(event_id=event_id, event_type=event_type))
    return customer
