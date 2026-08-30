import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

from search_service.config import Settings


class PublicSearchRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class PublicSearchRateLimitUnavailable(Exception):
    pass


class PublicSearchRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def check(self, client_ip: str) -> None:
        key = self._key(client_ip)
        try:
            requests = await self._client.incr(key)
            if requests == 1:
                await self._client.expire(key, self._settings.public_rate_limit_window_seconds)
            retry_after = max(await self._client.ttl(key), 1)
        except RedisError as exc:
            raise PublicSearchRateLimitUnavailable from exc
        if requests > self._settings.public_rate_limit:
            raise PublicSearchRateLimited(retry_after)

    @staticmethod
    def _key(client_ip: str) -> str:
        digest = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
        return f"fastapi-platform:search:public-query:v1:{digest}"
