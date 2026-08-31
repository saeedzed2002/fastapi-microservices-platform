import hashlib
import json
import secrets
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from identity_service.config import Settings


class PasswordResetError(Exception):
    """Base type for non-sensitive password-reset failures."""


class PasswordResetUnavailable(PasswordResetError):
    pass


class PasswordResetRateLimited(PasswordResetError):
    pass


class PasswordResetDeliveryUnavailable(PasswordResetError):
    pass


@dataclass(frozen=True)
class PasswordResetDelivery:
    delivery_id: UUID
    email: str
    token: str


class PasswordResetStateStore:
    """Keep a raw reset token only long enough for Notification to deliver it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Redis.from_url(settings.password_reset_redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def create_delivery(self, *, delivery_id: UUID, email: str) -> PasswordResetDelivery:
        digest = self._email_digest(email)
        cooldown_key = self._cooldown_key(digest)
        token = f"{delivery_id}.{secrets.token_urlsafe(48)}"
        delivery = PasswordResetDelivery(delivery_id=delivery_id, email=email, token=token)
        try:
            allowed = await self._client.set(
                cooldown_key,
                str(delivery_id),
                ex=self._settings.password_reset_resend_cooldown_seconds,
                nx=True,
            )
            if not allowed:
                raise PasswordResetRateLimited
            await self._client.set(
                self._delivery_key(delivery_id),
                json.dumps({"email": email, "token": token}, separators=(",", ":")),
                ex=self._settings.password_reset_token_ttl_seconds,
            )
        except PasswordResetRateLimited:
            raise
        except RedisError as exc:
            raise PasswordResetUnavailable from exc
        return delivery

    async def get_delivery(self, delivery_id: UUID) -> PasswordResetDelivery:
        try:
            raw_delivery = await self._client.get(self._delivery_key(delivery_id))
            if raw_delivery is None:
                raise PasswordResetDeliveryUnavailable
            decoded = json.loads(raw_delivery)
            email = decoded.get("email")
            token = decoded.get("token")
            if not isinstance(email, str) or not isinstance(token, str):
                raise PasswordResetDeliveryUnavailable
            return PasswordResetDelivery(delivery_id=delivery_id, email=email, token=token)
        except PasswordResetDeliveryUnavailable:
            raise
        except (RedisError, ValueError, TypeError) as exc:
            raise PasswordResetUnavailable from exc

    async def discard_delivery(self, delivery: PasswordResetDelivery) -> None:
        await self.discard_delivery_id(delivery.delivery_id)

    async def discard_delivery_id(self, delivery_id: UUID) -> None:
        try:
            await self._client.delete(self._delivery_key(delivery_id))
        except RedisError:
            return

    @staticmethod
    def parse_token(token: str) -> UUID:
        try:
            return UUID(token.split(".", 1)[0])
        except (IndexError, ValueError) as exc:
            raise ValueError("invalid password reset token") from exc

    @staticmethod
    def _email_digest(email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()

    @staticmethod
    def _delivery_key(delivery_id: UUID) -> str:
        return f"fastapi-platform:identity:password-reset:v1:delivery:{delivery_id}"

    @staticmethod
    def _cooldown_key(email_digest: str) -> str:
        return f"fastapi-platform:identity:password-reset:v1:cooldown:{email_digest}"
