import json
import logging
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from cart_service.config import Settings
from cart_service.schemas import CartResponse

logger = logging.getLogger("cart-service.cache")


class RedisCartCache:
    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.redis_cache_enabled
        self._ttl_seconds = settings.cart_cache_ttl_seconds
        self._client: Redis | None = (
            Redis.from_url(settings.redis_url, decode_responses=True) if self._enabled else None
        )

    @staticmethod
    def key(customer_id: UUID) -> str:
        return f"cart:v1:{customer_id}"

    async def get(self, customer_id: UUID) -> CartResponse | None:
        if self._client is None:
            return None
        try:
            value = await self._client.get(self.key(customer_id))
            return CartResponse.model_validate_json(value) if value else None
        except (RedisError, OSError, ValueError):
            logger.warning("cart_cache_read_failed", exc_info=True)
            return None

    async def set(self, response: CartResponse) -> None:
        if self._client is None:
            return
        try:
            payload = json.dumps(response.model_dump(mode="json"), separators=(",", ":"))
            await self._client.set(self.key(response.customer_id), payload, ex=self._ttl_seconds)
        except (RedisError, OSError):
            logger.warning("cart_cache_write_failed", exc_info=True)

    async def invalidate(self, customer_id: UUID) -> None:
        if self._client is None:
            return
        try:
            await self._client.delete(self.key(customer_id))
        except (RedisError, OSError):
            logger.warning("cart_cache_invalidation_failed", exc_info=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
