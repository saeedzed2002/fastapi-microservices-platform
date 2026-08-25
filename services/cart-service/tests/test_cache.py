import asyncio
from typing import cast
from uuid import uuid4

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from cart_service.cache import RedisCartCache
from cart_service.config import Settings


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
