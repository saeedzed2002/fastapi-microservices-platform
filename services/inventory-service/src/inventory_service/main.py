import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from inventory_service.application import (
    OrderGatewayUnavailable,
    adjust_stock,
    create_stock_item,
    list_stock_movements,
    load_stock_item_or_404,
    reconcile_confirmed_reservations,
    stock_item_response,
)
from inventory_service.auth import bearer, current_user, require_administrator
from inventory_service.config import get_settings
from inventory_service.db import dispose_engine, get_session
from inventory_service.schemas import (
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    StockItemCreate,
    StockItemResponse,
    StockMovementResponse,
    StockReconciliationResponse,
)
from inventory_service.workers.kafka import consume_saga_events, publish_outbox
from platform_auth import AuthClaims
from platform_observability import configure_application, metrics_response

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


app = FastAPI(title="Inventory Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
    log_level=settings.log_level,
)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post(
    "/api/v1/inventory/stock-items",
    response_model=StockItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_item_endpoint(
    payload: StockItemCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> StockItemResponse:
    require_administrator(claims)
    return stock_item_response(await create_stock_item(db, payload))


@app.get("/api/v1/inventory/stock-items/{sku}", response_model=StockItemResponse)
async def get_stock_item_endpoint(
    sku: str,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> StockItemResponse:
    require_administrator(claims)
    return stock_item_response(await load_stock_item_or_404(db, sku))


@app.post(
    "/api/v1/inventory/stock-items/{sku}/adjustments",
    response_model=StockAdjustmentResponse,
)
async def adjust_stock_endpoint(
    sku: str,
    payload: StockAdjustmentCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> StockAdjustmentResponse:
    require_administrator(claims)
    return await adjust_stock(db, sku, payload)


@app.get(
    "/api/v1/inventory/stock-items/{sku}/movements",
    response_model=list[StockMovementResponse],
)
async def list_stock_movements_endpoint(
    sku: str,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> list[StockMovementResponse]:
    require_administrator(claims)
    stock_item = await load_stock_item_or_404(db, sku)
    return await list_stock_movements(db, stock_item.id)


@app.post(
    "/api/v1/inventory/admin/reconcile-confirmed-reservations",
    response_model=StockReconciliationResponse,
)
async def reconcile_confirmed_reservations_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    claims: AuthClaims = Depends(current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> StockReconciliationResponse:
    require_administrator(claims)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        result = await reconcile_confirmed_reservations(
            db,
            order_base_url=settings.order_base_url,
            timeout_seconds=settings.order_request_timeout_seconds,
            access_token=credentials.credentials,
            limit=limit,
        )
    except OrderGatewayUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="order lookup unavailable",
        ) from exc
    return StockReconciliationResponse(scanned=result.scanned, committed=result.committed)


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()
