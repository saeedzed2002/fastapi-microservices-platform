import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError
from starlette.requests import Request

from identity_service.config import Settings
from identity_service.main import app, create_session, refresh
from identity_service.models import RefreshSession, User
from identity_service.password_reset import (
    PasswordResetDeliveryUnavailable,
    PasswordResetRateLimited,
    PasswordResetStateStore,
    PasswordResetUnavailable,
)
from identity_service.schemas import RefreshRequest
from identity_service.security import token_hash


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def aclose(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted


class UnavailableRedis:
    async def set(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise RedisError("unavailable")


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


class RefreshReuseDb:
    def __init__(self, session: RefreshSession) -> None:
        self._session = session
        self.executed: list[object] = []
        self.commit_count = 0

    async def scalar(self, statement: object) -> RefreshSession:
        del statement
        return self._session

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def commit(self) -> None:
        self.commit_count += 1


def test_password_reset_raw_token_is_limited_to_identity_delivery_state() -> None:
    async def exercise() -> None:
        store = PasswordResetStateStore(Settings())
        fake_redis = FakeRedis()
        store._client = fake_redis  # type: ignore[assignment]
        delivery_id = UUID("11111111-1111-4111-8111-111111111111")
        delivery = await store.create_delivery(
            delivery_id=delivery_id,
            email="admin@example.com",
        )

        cooldown_key = store._cooldown_key(store._email_digest(delivery.email))
        assert delivery.email not in cooldown_key
        assert delivery.token not in cooldown_key
        raw_delivery = json.loads(fake_redis.values[store._delivery_key(delivery_id)])
        assert raw_delivery == {"email": delivery.email, "token": delivery.token}
        assert await store.get_delivery(delivery_id) == delivery

        await store.discard_delivery_id(delivery_id)
        with pytest.raises(PasswordResetDeliveryUnavailable):
            await store.get_delivery(delivery_id)

    asyncio.run(exercise())


def test_password_reset_cooldown_and_redis_failure_fail_closed() -> None:
    async def exercise() -> None:
        store = PasswordResetStateStore(Settings())
        fake_redis = FakeRedis()
        store._client = fake_redis  # type: ignore[assignment]
        await store.create_delivery(delivery_id=uuid4(), email="admin@example.com")
        with pytest.raises(PasswordResetRateLimited):
            await store.create_delivery(delivery_id=uuid4(), email="admin@example.com")

        unavailable_store = PasswordResetStateStore(Settings())
        unavailable_store._client = UnavailableRedis()  # type: ignore[assignment]
        with pytest.raises(PasswordResetUnavailable):
            await unavailable_store.create_delivery(delivery_id=uuid4(), email="admin@example.com")

    asyncio.run(exercise())


def test_session_metadata_is_bounded_and_never_stores_raw_peer_address() -> None:
    async def exercise() -> None:
        db = RecordingSession()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "headers": [(b"user-agent", b"test-device")],
                "client": ("198.51.100.7", 54321),
            }
        )
        refresh_token = await create_session(db, user=User(id=uuid4()), request=request)

        stored_session = db.added[0]
        assert refresh_token != stored_session.token_hash  # type: ignore[union-attr]
        assert stored_session.user_agent == "test-device"  # type: ignore[union-attr]
        assert stored_session.ip_hash is not None  # type: ignore[union-attr]
        assert stored_session.ip_hash != "198.51.100.7"  # type: ignore[union-attr]
        assert len(stored_session.ip_hash) == 64  # type: ignore[arg-type,union-attr]

    asyncio.run(exercise())


def test_verified_refresh_reuse_revokes_the_remaining_token_family() -> None:
    async def exercise() -> None:
        session_id = UUID("11111111-1111-4111-8111-111111111111")
        refresh_token = f"{session_id}.replacement-token-material-at-least-32-bytes"
        db = RefreshReuseDb(
            RefreshSession(
                id=session_id,
                user_id=uuid4(),
                family_id=uuid4(),
                token_hash=token_hash(refresh_token),
                expires_at=datetime.now(UTC) + timedelta(days=1),
                revoked_at=datetime.now(UTC),
            )
        )
        request = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/refresh"})

        with pytest.raises(HTTPException) as exc_info:
            await refresh(RefreshRequest(refresh_token=refresh_token), request=request, db=db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 401
        assert len(db.executed) == 1
        assert db.commit_count == 1

    asyncio.run(exercise())


def test_identity_openapi_exposes_reset_and_session_lifecycle_but_not_raw_delivery() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/password-reset/request" in paths
    assert "/api/v1/auth/password-reset/confirm" in paths
    assert "/api/v1/auth/sessions" in paths
    assert "/api/v1/auth/sessions/{session_id}" in paths
    assert "/api/v1/auth/sessions/revoke-all" in paths
    assert "/internal/v1/password-reset-deliveries/{delivery_id}" not in paths
