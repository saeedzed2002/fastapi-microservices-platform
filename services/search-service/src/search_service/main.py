import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from search_service.application import search_products
from search_service.config import get_settings
from search_service.db import dispose_engine, get_session
from search_service.rate_limit import (
    PublicSearchRateLimited,
    PublicSearchRateLimiter,
    PublicSearchRateLimitUnavailable,
)
from search_service.schemas import SearchProductsResponse
from search_service.workers.kafka import consume_catalog_events

settings = get_settings()
logger = logging.getLogger(settings.service_name)
public_rate_limiter = PublicSearchRateLimiter(settings)


def source_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client is not None else "unknown"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if settings.kafka_consumer_enabled:
        task = asyncio.create_task(consume_catalog_events(settings, stop))
    logger.info("service_started")
    yield
    stop.set()
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await public_rate_limiter.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Search Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    try:
        await public_rate_limiter._client.ping()  # noqa: SLF001 - readiness owns the dependency check.
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="search rate limit unavailable"
        ) from exc
    return {"status": "ok"}


@app.get("/api/v1/search/products", response_model=SearchProductsResponse)
async def search_products_endpoint(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    cursor: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=20, ge=1, le=100),
    category_id: UUID | None = Query(default=None),
    brand_id: UUID | None = Query(default=None),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    min_price: Decimal | None = Query(default=None, ge=0, max_digits=12, decimal_places=2),
    max_price: Decimal | None = Query(default=None, ge=0, max_digits=12, decimal_places=2),
    db: AsyncSession = Depends(get_session),
) -> SearchProductsResponse:
    try:
        await public_rate_limiter.check(source_ip(request))
    except PublicSearchRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="search rate limit exceeded",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except PublicSearchRateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search is temporarily unavailable",
        ) from exc
    return await search_products(
        db,
        query=q.strip(),
        cursor=cursor,
        limit=limit,
        category_id=category_id,
        brand_id=brand_id,
        currency=currency,
        min_price=min_price,
        max_price=max_price,
    )


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP search_service_up Service availability\n"
        "# TYPE search_service_up gauge\n"
        "search_service_up 1\n"
    )
