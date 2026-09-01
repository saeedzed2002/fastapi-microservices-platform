import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_observability import configure_application, metrics_response
from shipping_service.config import get_settings
from shipping_service.db import dispose_engine, get_session

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("service_started")
    yield
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Shipping Service", version=settings.service_version, lifespan=lifespan)
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


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()
