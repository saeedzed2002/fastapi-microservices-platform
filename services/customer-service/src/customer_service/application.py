from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.models import Customer


async def provision_customer(db: AsyncSession, *, user_id: UUID, email: str) -> Customer:
    customer = await db.get(Customer, user_id)
    if customer is None:
        customer = Customer(id=user_id, email=email, display_name=email.split("@", 1)[0])
        db.add(customer)
    else:
        customer.email = email
    return customer
