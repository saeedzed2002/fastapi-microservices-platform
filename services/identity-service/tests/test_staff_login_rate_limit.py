import asyncio

import pytest
from redis.exceptions import RedisError

from identity_service.config import Settings
from identity_service.staff_login_rate_limit import (
    StaffLoginRateLimited,
    StaffLoginRateLimiter,
    StaffLoginRateLimitUnavailable,
)


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

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted


class UnavailableRedis:
    async def get(self, key: str) -> str | None:
        del key
        raise RedisError("unavailable")


def test_staff_login_limiter_locks_without_storing_raw_email() -> None:
    async def exercise() -> None:
        limiter = StaffLoginRateLimiter(
            Settings(
                staff_login_max_failures=2,
                staff_login_failure_window_seconds=60,
                staff_login_lockout_seconds=90,
            )
        )
        fake_redis = FakeRedis()
        limiter._client = fake_redis  # type: ignore[assignment]

        await limiter.check_allowed(email="admin@example.com")
        assert await limiter.record_failure(email="admin@example.com") is None
        assert await limiter.record_failure(email="admin@example.com") == 90
        assert all("admin@example.com" not in key for key in fake_redis.values)
        with pytest.raises(StaffLoginRateLimited):
            await limiter.check_allowed(email="admin@example.com")

    asyncio.run(exercise())


def test_staff_login_limiter_fails_closed_when_redis_is_unavailable() -> None:
    async def exercise() -> None:
        limiter = StaffLoginRateLimiter(Settings())
        limiter._client = UnavailableRedis()  # type: ignore[assignment]

        with pytest.raises(StaffLoginRateLimitUnavailable):
            await limiter.check_allowed(email="admin@example.com")

    asyncio.run(exercise())
