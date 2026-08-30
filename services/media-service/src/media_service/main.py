import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from media_service.application import (
    asset_response,
    authorize_upload,
    chat_attachment_download_url,
    complete_upload,
    load_owned_asset_or_404,
    validate_catalog_attachment,
)
from media_service.auth import current_user
from media_service.catalog_access import verify_catalog_access_proof
from media_service.chat_access import verify_chat_access_proof
from media_service.config import get_settings
from media_service.db import dispose_engine, get_session
from media_service.schemas import (
    InternalCatalogAttachmentRequest,
    InternalCatalogAttachmentResponse,
    InternalChatAttachmentDownloadRequest,
    InternalChatAttachmentDownloadResponse,
    MediaAssetResponse,
    UploadAuthorization,
    UploadRequest,
)
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


@app.post(
    "/api/internal/v1/media/chat-attachments/{asset_id}/download-url",
    response_model=InternalChatAttachmentDownloadResponse,
)
async def create_chat_attachment_download_url(
    asset_id: UUID,
    payload: InternalChatAttachmentDownloadRequest,
    chat_access_proof: str = Header(alias="X-Chat-Access-Proof"),
    db: AsyncSession = Depends(get_session),
) -> InternalChatAttachmentDownloadResponse:
    verify_chat_access_proof(
        settings=settings,
        provided_proof=chat_access_proof,
        subject_id=payload.subject_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        asset_id=asset_id,
        expires_at=payload.expires_at,
    )
    download_url, content_type, size_bytes = await chat_attachment_download_url(
        db, asset_id=asset_id, storage=storage, settings=settings
    )
    return InternalChatAttachmentDownloadResponse(
        asset_id=asset_id,
        content_type=content_type,
        size_bytes=size_bytes,
        download_url=download_url,
    )


@app.post(
    "/api/internal/v1/media/catalog-assets/{asset_id}/attachment-availability",
    response_model=InternalCatalogAttachmentResponse,
)
async def validate_catalog_asset_attachment(
    asset_id: UUID,
    payload: InternalCatalogAttachmentRequest,
    catalog_access_proof: str = Header(alias="X-Catalog-Access-Proof"),
    db: AsyncSession = Depends(get_session),
) -> InternalCatalogAttachmentResponse:
    verify_catalog_access_proof(
        settings=settings,
        provided_proof=catalog_access_proof,
        subject_id=payload.owner_subject_id,
        asset_id=asset_id,
        expires_at=payload.expires_at,
    )
    asset = await validate_catalog_attachment(
        db,
        asset_id=asset_id,
        owner_subject_id=payload.owner_subject_id,
    )
    return InternalCatalogAttachmentResponse(asset_id=asset.id)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP media_service_up Service availability\n"
        "# TYPE media_service_up gauge\n"
        "media_service_up 1\n"
    )
