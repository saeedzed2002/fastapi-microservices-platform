import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

from identity_service.config import Settings


class StaffLoginRateLimitUnavailable(Exception):
    pass


class StaffLoginRateLimited(Exception):
    pass


class StaffLoginRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Redis.from_url(settings.otp_redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def check_allowed(self, *, email: str) -> None:
        try:
            if await self._client.get(self._lock_key(email)) is not None:
                raise StaffLoginRateLimited
        except StaffLoginRateLimited:
            raise
        except RedisError as exc:
            raise StaffLoginRateLimitUnavailable from exc

    async def record_failure(self, *, email: str) -> int | None:
        failure_key = self._failure_key(email)
        try:
            failures = await self._client.incr(failure_key)
            if failures == 1:
                await self._client.expire(
                    failure_key, self._settings.staff_login_failure_window_seconds
                )
            if failures < self._settings.staff_login_max_failures:
                return None
            await self._client.set(
                self._lock_key(email),
                "1",
                ex=self._settings.staff_login_lockout_seconds,
            )
            await self._client.delete(failure_key)
            return self._settings.staff_login_lockout_seconds
        except RedisError as exc:
            raise StaffLoginRateLimitUnavailable from exc

    async def record_success(self, *, email: str) -> None:
        try:
            await self._client.delete(self._failure_key(email))
        except RedisError as exc:
            raise StaffLoginRateLimitUnavailable from exc

    @staticmethod
    def _email_digest(email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()

    @classmethod
    def _failure_key(cls, email: str) -> str:
        return f"fastapi-platform:identity:staff-login:v1:failures:{cls._email_digest(email)}"

    @classmethod
    def _lock_key(cls, email: str) -> str:
        return f"fastapi-platform:identity:staff-login:v1:lock:{cls._email_digest(email)}"
