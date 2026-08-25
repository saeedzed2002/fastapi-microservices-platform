import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from media_service.application import (
    asset_response,
    authorize_upload,
    complete_upload,
    load_owned_asset_or_404,
)
from media_service.auth import current_user
from media_service.config import get_settings
from media_service.db import dispose_engine, get_session
from media_service.schemas import MediaAssetResponse, UploadAuthorization, UploadRequest
from media_service.storage import S3ObjectStorage
from media_service.workers.outbox_publisher import run_outbox_publisher
from media_service.workers.task_dispatcher import run_task_dispatcher
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)
storage = S3ObjectStorage(settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_publisher_enabled:
        tasks.append(asyncio.create_task(run_outbox_publisher(settings, stop)))
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


app = FastAPI(title="Media Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/v1/media/uploads", response_model=UploadAuthorization, status_code=201)
async def create_upload(
    payload: UploadRequest,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> UploadAuthorization:
    return await authorize_upload(
        db,
        owner_subject_id=claims.subject,
        payload=payload,
        storage=storage,
        settings=settings,
    )


@app.post("/api/v1/media/assets/{asset_id}/complete", status_code=202)
async def complete(
    asset_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    asset = await load_owned_asset_or_404(db, asset_id=asset_id, owner_subject_id=claims.subject)
    await complete_upload(db, asset=asset, storage=storage)
    return {"status": "accepted"}


@app.get("/api/v1/media/assets/{asset_id}", response_model=MediaAssetResponse)
async def get_asset(
    asset_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> MediaAssetResponse:
    asset = await load_owned_asset_or_404(db, asset_id=asset_id, owner_subject_id=claims.subject)
    return await asset_response(db, asset=asset, storage=storage, settings=settings)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP media_service_up Service availability\n"
        "# TYPE media_service_up gauge\n"
        "media_service_up 1\n"
    )
