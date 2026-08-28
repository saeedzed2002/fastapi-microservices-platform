import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from identity_service.application import provision_support_agent, update_support_agent_status
from identity_service.main import current_active_administrator
from identity_service.models import AuthenticationAuditEvent, User
from platform_auth import AuthClaims


class FakeSession:
    def __init__(self, *, scalar_result: User | None = None) -> None:
        self.scalar_result = scalar_result
        self.added: list[object] = []
        self.executed: list[object] = []

    async def scalar(self, statement: object) -> User | None:
        del statement
        return self.scalar_result

    async def flush(self) -> None:
        for value in self.added:
            if isinstance(value, User) and value.id is None:
                value.id = uuid4()

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def get(self, model: type[User], user_id: UUID) -> User | None:
        del model, user_id
        return self.scalar_result

    def add(self, value: object) -> None:
        self.added.append(value)


def test_provision_support_agent_creates_audit_event() -> None:
    async def exercise() -> None:
        session = FakeSession()
        actor_id = uuid4()

        agent = await provision_support_agent(
            db=session,  # type: ignore[arg-type]
            actor_user_id=actor_id,
            email="agent@example.com",
            password="correct horse battery staple",
        )

        audit = next(
            value for value in session.added if isinstance(value, AuthenticationAuditEvent)
        )
        assert agent.roles == ["support_agent"]
        assert agent.password_hash is not None
        assert audit.actor_user_id == actor_id
        assert audit.target_user_id == agent.id
        assert audit.event_type == "identity.support_agent.provisioned.v1"

    asyncio.run(exercise())


def test_suspending_support_agent_revokes_refresh_sessions_and_audits() -> None:
    async def exercise() -> None:
        agent = User(
            id=uuid4(),
            email="agent@example.com",
            phone=None,
            password_hash="stored-hash",
            status="active",
            roles=["support_agent"],
        )
        session = FakeSession(scalar_result=agent)
        actor_id = uuid4()

        updated = await update_support_agent_status(
            db=session,  # type: ignore[arg-type]
            actor_user_id=actor_id,
            support_agent_id=agent.id,
            status="suspended",
        )

        audit = next(
            value for value in session.added if isinstance(value, AuthenticationAuditEvent)
        )
        assert updated.status == "suspended"
        assert len(session.executed) == 1
        assert audit.actor_user_id == actor_id
        assert audit.target_user_id == agent.id
        assert audit.event_type == "identity.support_agent.status_changed.v1"
        assert audit.details == {"previous_status": "active", "status": "suspended"}

    asyncio.run(exercise())


def test_current_active_administrator_checks_signed_role_and_local_state() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        administrator = User(
            id=uuid4(),
            email="admin@example.com",
            phone=None,
            password_hash="stored-hash",
            status="active",
            roles=["admin"],
        )
        claims = AuthClaims(
            subject=administrator.id,
            token_id=uuid4(),
            roles=("admin",),
            issued_at=now,
            expires_at=now + timedelta(minutes=15),
        )

        assert (
            await current_active_administrator(
                claims=claims,
                db=FakeSession(scalar_result=administrator),  # type: ignore[arg-type]
            )
            is administrator
        )

        non_admin_claims = AuthClaims(
            subject=administrator.id,
            token_id=uuid4(),
            roles=("support_agent",),
            issued_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        with pytest.raises(HTTPException) as error:
            await current_active_administrator(
                claims=non_admin_claims,
                db=FakeSession(scalar_result=administrator),  # type: ignore[arg-type]
            )
        assert error.value.status_code == 403

    asyncio.run(exercise())
