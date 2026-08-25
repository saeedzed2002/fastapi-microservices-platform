import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from order_service.application import (
    collect_checkout_snapshot,
    create_order,
    load_owned_order_or_404,
    order_response,
)
from order_service.auth import bearer, current_user
from order_service.config import get_settings
from order_service.db import dispose_engine, get_session
from order_service.schemas import CheckoutRequest, OrderResponse
from order_service.workers.kafka import consume_saga_events, publish_outbox
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_publisher_enabled:
        tasks.append(asyncio.create_task(publish_outbox(settings, stop)))
    if settings.kafka_consumer_enabled:
        tasks.append(asyncio.create_task(consume_saga_events(settings, stop)))
    logger.info("service_started")
    yield
    stop.set()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Order Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    return await order_response(db, await load_owned_order_or_404(db, order_id, claims.subject))


@app.post("/api/v1/orders", response_model=OrderResponse, status_code=status.HTTP_202_ACCEPTED)
async def checkout(
    payload: CheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    quantities: dict[UUID, int] = {}
    for item in payload.items:
        if item.variant_id in quantities:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duplicate variant"
            )
        quantities[item.variant_id] = item.quantity
    address, snapshots, currency, total = await collect_checkout_snapshot(
        catalog_base_url=settings.catalog_base_url,
        customer_base_url=settings.customer_base_url,
        access_token=credentials.credentials,
        address_id=payload.address_id,
        item_quantities=quantities,
    )
    return await order_response(
        db,
        await create_order(
            db,
            customer_id=claims.subject,
            idempotency_key=idempotency_key,
            delivery_address=address,
            snapshots=snapshots,
            currency=currency,
            total_amount=total,
            payment_method=payload.payment_method,
        ),
    )


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP order_service_up Service availability\n"
        "# TYPE order_service_up gauge\n"
        "order_service_up 1\n"
    )
