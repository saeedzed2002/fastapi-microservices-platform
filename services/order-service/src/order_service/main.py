import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from order_service.application import (
    admin_order_response,
    collect_checkout_snapshot,
    create_order,
    list_administrator_orders,
    list_customer_orders,
    load_order_or_404,
    load_owned_order_or_404,
    order_response,
    validate_checkout_payment,
)
from order_service.auth import bearer, require_administrator, require_customer
from order_service.config import get_settings
from order_service.db import dispose_engine, get_session
from order_service.schemas import (
    AdminOrderPage,
    AdminOrderResponse,
    CheckoutRequest,
    CustomerOrderPage,
    OrderResponse,
    OrderStatus,
)
from order_service.workers.kafka import consume_invoice_events, consume_saga_events, publish_outbox
from order_service.workers.task_dispatcher import run_task_dispatcher
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
    if settings.invoice_consumer_enabled:
        tasks.append(asyncio.create_task(consume_invoice_events(settings, stop)))
    if settings.task_dispatcher_enabled:
        tasks.append(asyncio.create_task(run_task_dispatcher(settings, stop)))
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


@app.get("/api/v1/orders/admin", response_model=AdminOrderPage)
async def get_administrator_orders(
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    _: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> AdminOrderPage:
    try:
        return await list_administrator_orders(
            db=db,
            status_filter=order_status,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from exc


@app.get("/api/v1/orders/admin/{order_id}", response_model=AdminOrderResponse)
async def get_administrator_order(
    order_id: UUID,
    _: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> AdminOrderResponse:
    return await admin_order_response(db, await load_order_or_404(db, order_id))


@app.get("/api/v1/orders", response_model=CustomerOrderPage)
async def get_customer_orders(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CustomerOrderPage:
    try:
        return await list_customer_orders(
            db=db,
            customer_id=claims.subject,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from exc


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    return await order_response(db, await load_owned_order_or_404(db, order_id, claims.subject))


@app.post("/api/v1/orders", response_model=OrderResponse, status_code=status.HTTP_202_ACCEPTED)
async def checkout(
    payload: CheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_customer),
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
    address, customer_email, snapshots, currency, total = await collect_checkout_snapshot(
        catalog_base_url=settings.catalog_base_url,
        customer_base_url=settings.customer_base_url,
        access_token=credentials.credentials,
        address_id=payload.address_id,
        item_quantities=quantities,
    )
    validate_checkout_payment(
        payment_method=payload.payment_method, currency=currency, total_amount=total
    )
    return await order_response(
        db,
        await create_order(
            db,
            customer_id=claims.subject,
            idempotency_key=idempotency_key,
            delivery_address=address,
            customer_email=customer_email,
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
