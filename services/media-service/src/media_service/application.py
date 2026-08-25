from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from media_service.config import Settings
from media_service.models import MediaAsset, MediaDerivative, MediaTaskIntent
from media_service.schemas import (
    DerivativeResponse,
    MediaAssetResponse,
    UploadAuthorization,
    UploadRequest,
)
from media_service.storage import ObjectStorage


async def load_owned_asset_or_404(
    db: AsyncSession, *, asset_id: UUID, owner_subject_id: UUID
) -> MediaAsset:
    asset = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.owner_subject_id == owner_subject_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media asset not found")
    return asset


async def authorize_upload(
    db: AsyncSession,
    *,
    owner_subject_id: UUID,
    payload: UploadRequest,
    storage: ObjectStorage,
    settings: Settings,
) -> UploadAuthorization:
    if payload.size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="upload exceeds limit"
        )
    asset_id = uuid4()
    key = f"uploads/{owner_subject_id}/{asset_id}/original"
    asset = MediaAsset(
        id=asset_id,
        owner_subject_id=owner_subject_id,
        purpose=payload.purpose,
        original_object_key=key,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
    )
    db.add(asset)
    await db.commit()
    try:
        storage.ensure_bucket()
        url = storage.create_upload_url(
            object_key=key,
            content_type=payload.content_type,
            expires_in=settings.upload_url_ttl_seconds,
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="object storage unavailable"
        ) from exc
    return UploadAuthorization(
        asset_id=asset.id,
        upload_url=url,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.upload_url_ttl_seconds),
    )


async def complete_upload(db: AsyncSession, *, asset: MediaAsset, storage: ObjectStorage) -> None:
    if asset.status == "ready":
        return
    if asset.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="media asset is not completable"
        )
    try:
        object_head = storage.head(object_key=asset.original_object_key)
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="uploaded object was not found"
        ) from exc
    if object_head.content_type != asset.content_type or object_head.size_bytes != asset.size_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uploaded object does not match authorization",
        )
    asset.status = "uploaded"
    db.add(
        MediaTaskIntent(
            task_name="media.process_asset.v1",
            payload={"media_asset_id": str(asset.id)},
        )
    )
    await db.commit()


async def asset_response(
    db: AsyncSession, *, asset: MediaAsset, storage: ObjectStorage, settings: Settings
) -> MediaAssetResponse:
    derivatives = list(
        await db.scalars(
            select(MediaDerivative)
            .where(MediaDerivative.media_asset_id == asset.id)
            .order_by(MediaDerivative.created_at)
        )
    )
    return MediaAssetResponse(
        id=asset.id,
        purpose=asset.purpose,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        status=asset.status,
        processing_error=asset.processing_error,
        created_at=asset.created_at,
        ready_at=asset.ready_at,
        derivatives=[
            DerivativeResponse(
                kind=derivative.kind,
                content_type=derivative.content_type,
                size_bytes=derivative.size_bytes,
                width=derivative.width,
                height=derivative.height,
                download_url=(
                    storage.create_download_url(
                        object_key=derivative.object_key,
                        expires_in=settings.upload_url_ttl_seconds,
                    )
                    if asset.status == "ready"
                    else None
                ),
            )
            for derivative in derivatives
        ],
    )
