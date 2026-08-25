import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.config import get_settings
from notification_service.db import dispose_engine, get_session
from notification_service.workers.kafka import consume_invoice_events
from notification_service.workers.task_dispatcher import run_task_dispatcher

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_consumer_enabled:
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


app = FastAPI(title="Notification Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP notification_service_up Service availability\n"
        "# TYPE notification_service_up gauge\n"
        "notification_service_up 1\n"
    )
