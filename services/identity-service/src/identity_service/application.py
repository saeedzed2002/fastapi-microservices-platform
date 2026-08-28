from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import cast, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.config import Settings
from identity_service.models import AuthenticationAuditEvent, OutboxMessage, RefreshSession, User
from identity_service.notification import NotificationOtpGateway, NotificationUnavailable
from identity_service.otp import OtpStateStore
from identity_service.security import hash_password


class AdminAlreadyExists(Exception):
    pass


class OtpDeliveryUnavailable(Exception):
    pass


class OtpNotEligible(Exception):
    pass


class SupportAgentAlreadyExists(Exception):
    pass


class SupportAgentNotFound(Exception):
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


async def provision_support_agent(
    *, db: AsyncSession, actor_user_id: UUID, email: str, password: str
) -> User:
    existing = await db.scalar(select(User).where(User.email == email).with_for_update())
    if existing is not None:
        raise SupportAgentAlreadyExists
    user = User(
        email=email,
        phone=None,
        password_hash=hash_password(password),
        roles=["support_agent"],
    )
    db.add(user)
    await db.flush()
    db.add(
        AuthenticationAuditEvent(
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            event_type="identity.support_agent.provisioned.v1",
            details={"status": user.status},
        )
    )
    return user


async def list_support_agents(*, db: AsyncSession, limit: int) -> list[User]:
    rows = await db.scalars(
        select(User)
        .where(cast(User.roles, JSONB).contains(["support_agent"]))
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
    )
    return list(rows)


async def update_support_agent_status(
    *,
    db: AsyncSession,
    actor_user_id: UUID,
    support_agent_id: UUID,
    status: Literal["active", "suspended"],
) -> User:
    user = await db.scalar(select(User).where(User.id == support_agent_id).with_for_update())
    if user is None or user.roles != ["support_agent"]:
        raise SupportAgentNotFound
    previous_status = user.status
    if previous_status == status:
        return user
    user.status = status
    if status == "suspended":
        await db.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    db.add(
        AuthenticationAuditEvent(
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            event_type="identity.support_agent.status_changed.v1",
            details={"previous_status": previous_status, "status": status},
        )
    )
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
