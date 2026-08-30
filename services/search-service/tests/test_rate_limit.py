import asyncio

from search_service.config import Settings
from search_service.rate_limit import PublicSearchRateLimited, PublicSearchRateLimiter


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        del key, seconds

    async def ttl(self, key: str) -> int:
        del key
        return 60


def test_public_search_limit_uses_hashed_source_ip() -> None:
    async def scenario() -> None:
        limiter = PublicSearchRateLimiter(
            Settings(public_rate_limit=1, public_rate_limit_window_seconds=60)
        )
        fake = FakeRedis()
        limiter._client = fake  # type: ignore[assignment]
        await limiter.check("203.0.113.8")
        try:
            await limiter.check("203.0.113.8")
        except PublicSearchRateLimited as exc:
            assert exc.retry_after == 60
        else:
            raise AssertionError("second request was not rate limited")
        assert all("203.0.113.8" not in key for key in fake.values)

    asyncio.run(scenario())
