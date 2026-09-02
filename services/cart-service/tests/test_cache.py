import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from cart_service.cache import RedisCartCache
from cart_service.config import Settings
from cart_service.schemas import CartItemResponse, CartResponse


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.ttls[key] = ex

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return int(self.values.pop(key, None) is not None)


def _cart_response() -> CartResponse:
    now = datetime.now(UTC)
    customer_id = uuid4()
    return CartResponse(
        id=uuid4(),
        customer_id=customer_id,
        status="active",
        version=3,
        items=[
            CartItemResponse(
                id=uuid4(),
                variant_id=uuid4(),
                quantity=2,
                created_at=now,
                updated_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )


def test_disabled_cache_is_a_noop() -> None:
    async def exercise() -> None:
        cache = RedisCartCache(Settings(redis_cache_enabled=False))
        assert await cache.get(uuid4()) is None
        await cache.invalidate(uuid4())
        await cache.close()

    asyncio.run(exercise())


def test_cache_connection_error_falls_open() -> None:
    class FailingRedis:
        async def get(self, _: str) -> str:
            raise RedisConnectionError("unavailable")

    async def exercise() -> None:
        cache = RedisCartCache(Settings())
        cache._client = cast(Redis, FailingRedis())
        assert await cache.get(uuid4()) is None

    asyncio.run(exercise())


def test_cache_round_trip_uses_customer_scoped_key_and_configured_ttl() -> None:
    async def exercise() -> None:
        settings = Settings(cart_cache_ttl_seconds=123)
        cache = RedisCartCache(settings)
        redis = MemoryRedis()
        cache._client = cast(Redis, redis)
        response = _cart_response()

        await cache.set(response)

        key = cache.key(response.customer_id)
        assert redis.ttls[key] == 123
        assert await cache.get(response.customer_id) == response
        await cache.invalidate(response.customer_id)
        assert await cache.get(response.customer_id) is None

    asyncio.run(exercise())


def test_cache_corrupt_payload_and_write_failures_do_not_break_durable_cart_operations() -> None:
    class FailingRedis:
        async def get(self, _: str) -> str:
            return "not-json"

        async def set(self, *_: object, **__: object) -> None:
            raise RedisConnectionError("unavailable")

        async def delete(self, _: str) -> None:
            raise RedisConnectionError("unavailable")

    async def exercise() -> None:
        cache = RedisCartCache(Settings())
        cache._client = cast(Redis, FailingRedis())
        response = _cart_response()

        assert await cache.get(response.customer_id) is None
        await cache.set(response)
        await cache.invalidate(response.customer_id)

    asyncio.run(exercise())
