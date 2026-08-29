import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cart_service.application import (
    add_item,
    clear_cart,
    consume_cart_items,
    delete_item,
    get_cart,
    update_item,
)
from cart_service.auth import require_customer
from cart_service.cache import RedisCartCache
from cart_service.config import get_settings
from cart_service.db import dispose_engine, get_session
from cart_service.schemas import CartConsumeRequest, CartItemCreate, CartItemUpdate, CartResponse
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)
cart_cache = RedisCartCache(settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    await cart_cache.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Cart Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/carts/me", response_model=CartResponse)
async def get_my_cart(
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await get_cart(db, claims.subject, cart_cache)


@app.post("/api/v1/carts/me/items", response_model=CartResponse)
async def add_cart_item(
    payload: CartItemCreate,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await add_item(db, claims.subject, payload, cart_cache)


@app.patch("/api/v1/carts/me/items/{variant_id}", response_model=CartResponse)
async def update_cart_item(
    variant_id: UUID,
    payload: CartItemUpdate,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await update_item(db, claims.subject, variant_id, payload, cart_cache)


@app.delete("/api/v1/carts/me/items/{variant_id}", response_model=CartResponse)
async def delete_cart_item(
    variant_id: UUID,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await delete_item(db, claims.subject, variant_id, cart_cache)


@app.delete("/api/v1/carts/me", response_model=CartResponse)
async def clear_my_cart(
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await clear_cart(db, claims.subject, cart_cache)


@app.post(
    "/api/v1/carts/me/consume",
    response_model=CartResponse,
    responses={status.HTTP_409_CONFLICT: {"description": "Cart changed during checkout"}},
)
async def consume_my_cart_items(
    payload: CartConsumeRequest,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CartResponse:
    return await consume_cart_items(db, claims.subject, payload, cart_cache)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP cart_service_up Service availability\n"
        "# TYPE cart_service_up gauge\n"
        "cart_service_up 1\n"
    )
