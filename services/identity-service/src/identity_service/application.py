from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.config import Settings
from identity_service.models import OutboxMessage, User
from identity_service.notification import NotificationOtpGateway, NotificationUnavailable
from identity_service.otp import OtpStateStore
from identity_service.security import hash_password


class AdminAlreadyExists(Exception):
    pass


class OtpDeliveryUnavailable(Exception):
    pass


class OtpNotEligible(Exception):
    pass


async def provision_administrator(*, db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is not None:
        raise AdminAlreadyExists
    user = User(
        email=email,
        phone=None,
        password_hash=hash_password(password),
        roles=["admin"],
    )
    db.add(user)
    await db.flush()
    return user


async def request_customer_otp(
    *,
    phone: str,
    state_store: OtpStateStore,
    notification_gateway: NotificationOtpGateway,
) -> None:
    challenge = await state_store.create_challenge(phone=phone, delivery_id=uuid4())
    try:
        await notification_gateway.enqueue(
            delivery_id=challenge.delivery_id,
            phone=challenge.phone,
        )
    except NotificationUnavailable as exc:
        await state_store.discard_challenge(challenge)
        raise OtpDeliveryUnavailable from exc


async def verify_customer_otp(
    *,
    db: AsyncSession,
    phone: str,
    code: str,
    state_store: OtpStateStore,
    settings: Settings,
) -> User:
    await state_store.verify_challenge(phone=phone, code=code)
    user = await db.scalar(select(User).where(User.phone == phone).with_for_update())
    if user is not None:
        if user.status != "active" or "customer" not in user.roles:
            raise OtpNotEligible
        return user

    user = User(phone=phone, email=None, password_hash=None, roles=["customer"])
    db.add(user)
    await db.flush()
    db.add(
        OutboxMessage(
            event_type="identity.user_registered.v2",
            aggregate_type="user",
            aggregate_id=user.id,
            payload={"user_id": str(user.id), "phone": user.phone, "roles": list(user.roles)},
            headers={"producer": settings.service_name},
        )
    )
    return user
