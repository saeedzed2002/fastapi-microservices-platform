import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from media_service.application import (
    asset_response,
    authorize_upload,
    chat_attachment_download_url,
    complete_upload,
    list_owned_assets,
    load_owned_asset_or_404,
    public_product_image_download_url,
    request_asset_deletion,
    validate_catalog_attachment,
)
from media_service.auth import current_user, require_administrator
from media_service.catalog import HttpCatalogMediaGateway
from media_service.catalog_access import verify_catalog_access_proof
from media_service.chat_access import verify_chat_access_proof
from media_service.config import get_settings
from media_service.db import dispose_engine, get_session
from media_service.schemas import (
    InternalCatalogAttachmentRequest,
    InternalCatalogAttachmentResponse,
    InternalChatAttachmentDownloadRequest,
    InternalChatAttachmentDownloadResponse,
    MediaAssetListResponse,
    MediaAssetResponse,
    UploadAuthorization,
    UploadRequest,
)
from media_service.storage import S3ObjectStorage
from media_service.workers.outbox_publisher import run_outbox_publisher
from media_service.workers.task_dispatcher import run_task_dispatcher
from platform_auth import AuthClaims
from platform_observability import configure_application, metrics_response

settings = get_settings()
logger = logging.getLogger(settings.service_name)
storage = S3ObjectStorage(settings)
catalog_gateway = HttpCatalogMediaGateway(settings)


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
    await catalog_gateway.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Media Service", version=settings.service_version, lifespan=lifespan)
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


@app.post("/api/v1/media/uploads", response_model=UploadAuthorization, status_code=201)
async def create_upload(
    payload: UploadRequest,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> UploadAuthorization:
    if payload.purpose == "product_image":
        require_administrator(claims)
    return await authorize_upload(
        db,
        owner_subject_id=claims.subject,
        payload=payload,
        storage=storage,
        settings=settings,
    )


@app.get("/api/v1/media/assets", response_model=MediaAssetListResponse)
async def list_assets(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> MediaAssetListResponse:
    return await list_owned_assets(
        db,
        owner_subject_id=claims.subject,
        cursor=cursor,
        limit=limit,
        storage=storage,
        settings=settings,
    )


@app.get("/api/v1/media/public/product-images/{asset_id}")
async def redirect_public_product_image(
    asset_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    return RedirectResponse(
        url=await public_product_image_download_url(
            db,
            asset_id=asset_id,
            storage=storage,
            settings=settings,
        ),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
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


@app.delete("/api/v1/media/assets/{asset_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_asset(
    asset_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    asset = await load_owned_asset_or_404(db, asset_id=asset_id, owner_subject_id=claims.subject)
    if asset.purpose == "product_image":
        require_administrator(claims)
        if await catalog_gateway.is_product_image_referenced(asset_id=asset.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="detach product images from Catalog before deleting the media asset",
            )
    await request_asset_deletion(db, asset=asset)
    return {"status": "deletion_pending"}


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
async def metrics() -> Response:
    return metrics_response()
