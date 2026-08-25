import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from inventory_service.application import (
    adjust_stock,
    create_stock_item,
    list_stock_movements,
    load_stock_item_or_404,
    stock_item_response,
)
from inventory_service.auth import current_user, require_inventory_admin
from inventory_service.config import get_settings
from inventory_service.db import dispose_engine, get_session
from inventory_service.schemas import (
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    StockItemCreate,
    StockItemResponse,
    StockMovementResponse,
)
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Inventory Service", version=settings.service_version, lifespan=lifespan)


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
    require_inventory_admin(claims)
    return stock_item_response(await create_stock_item(db, payload))


@app.get("/api/v1/inventory/stock-items/{sku}", response_model=StockItemResponse)
async def get_stock_item_endpoint(
    sku: str,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> StockItemResponse:
    require_inventory_admin(claims)
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
    require_inventory_admin(claims)
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
    require_inventory_admin(claims)
    stock_item = await load_stock_item_or_404(db, sku)
    return await list_stock_movements(db, stock_item.id)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP inventory_service_up Service availability\n"
        "# TYPE inventory_service_up gauge\n"
        "inventory_service_up 1\n"
    )
