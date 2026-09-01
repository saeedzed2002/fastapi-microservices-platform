import asyncio
import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from fastapi import HTTPException, status
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from media_service.config import Settings
from media_service.models import MediaAsset, MediaDerivative, MediaTaskIntent
from media_service.schemas import (
    DerivativeResponse,
    MediaAssetListResponse,
    MediaAssetResponse,
    UploadAuthorization,
    UploadRequest,
)
from media_service.storage import ObjectStorage


@dataclass(frozen=True)
class CleanupCandidate:
    asset_id: UUID
    object_keys: tuple[str, ...]


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
    asset_id = asset.id
    expected_content_type = asset.content_type
    expected_size_bytes = asset.size_bytes
    object_key = asset.original_object_key
    await db.rollback()
    try:
        object_head = await asyncio.to_thread(storage.head, object_key=object_key)
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="uploaded object was not found"
        ) from exc
    if (
        object_head.content_type != expected_content_type
        or object_head.size_bytes != expected_size_bytes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uploaded object does not match authorization",
        )
    reloaded_asset = await db.get(MediaAsset, asset_id, with_for_update=True)
    if reloaded_asset is None or reloaded_asset.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="media asset is not completable"
        )
    reloaded_asset.status = "uploaded"
    db.add(
        MediaTaskIntent(
            task_name="media.process_asset.v1",
            payload={"media_asset_id": str(reloaded_asset.id)},
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


def _encode_asset_cursor(asset: MediaAsset) -> str:
    payload = {
        "created_at": asset.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "asset_id": str(asset.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")


def _decode_asset_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        asset_id = UUID(str(payload["asset_id"]))
    except (binascii.Error, KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid media cursor",
        ) from exc
    if created_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid media cursor",
        )
    return created_at.astimezone(UTC), asset_id


async def list_owned_assets(
    db: AsyncSession,
    *,
    owner_subject_id: UUID,
    cursor: str | None,
    limit: int,
    storage: ObjectStorage,
    settings: Settings,
) -> MediaAssetListResponse:
    cursor_values = _decode_asset_cursor(cursor)
    conditions = [MediaAsset.owner_subject_id == owner_subject_id, MediaAsset.deleted_at.is_(None)]
    if cursor_values is not None:
        created_at, asset_id = cursor_values
        conditions.append(
            or_(
                MediaAsset.created_at < created_at,
                and_(MediaAsset.created_at == created_at, MediaAsset.id < asset_id),
            )
        )
    assets = list(
        await db.scalars(
            select(MediaAsset)
            .where(*conditions)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
            .limit(limit + 1)
        )
    )
    has_next_page = len(assets) > limit
    if has_next_page:
        assets = assets[:limit]
    return MediaAssetListResponse(
        items=[
            await asset_response(db, asset=asset, storage=storage, settings=settings)
            for asset in assets
        ],
        next_cursor=_encode_asset_cursor(assets[-1]) if has_next_page else None,
    )


async def public_product_image_download_url(
    db: AsyncSession, *, asset_id: UUID, storage: ObjectStorage, settings: Settings
) -> str:
    asset = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.purpose == "product_image",
            MediaAsset.status == "ready",
            MediaAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product image not found")
    derivative = await db.scalar(
        select(MediaDerivative).where(
            MediaDerivative.media_asset_id == asset.id,
            MediaDerivative.kind == "thumbnail",
        )
    )
    if derivative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product image not found")
    return storage.create_download_url(
        object_key=derivative.object_key,
        expires_in=settings.upload_url_ttl_seconds,
    )


async def request_asset_deletion(db: AsyncSession, *, asset: MediaAsset) -> None:
    if asset.status in {"deleted", "deletion_pending"}:
        return
    asset.status = "deletion_pending"
    db.add(
        MediaTaskIntent(
            task_name="media.delete_asset.v1",
            payload={"media_asset_id": str(asset.id)},
        )
    )
    await db.commit()


async def chat_attachment_download_url(
    db: AsyncSession, *, asset_id: UUID, storage: ObjectStorage, settings: Settings
) -> tuple[str, str, int]:
    asset = await db.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.deleted_at.is_(None))
    )
    if asset is None or asset.purpose != "chat_attachment" or asset.status != "ready":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media asset not found")
    derivative = await db.scalar(
        select(MediaDerivative).where(
            MediaDerivative.media_asset_id == asset.id,
            MediaDerivative.kind == "thumbnail",
        )
    )
    if derivative is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="media asset is not available"
        )
    return (
        storage.create_download_url(
            object_key=derivative.object_key,
            expires_in=settings.upload_url_ttl_seconds,
        ),
        derivative.content_type,
        derivative.size_bytes,
    )


async def validate_catalog_attachment(
    db: AsyncSession, *, asset_id: UUID, owner_subject_id: UUID
) -> MediaAsset:
    asset = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.owner_subject_id == owner_subject_id,
            MediaAsset.purpose == "product_image",
            MediaAsset.status == "ready",
            MediaAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="media asset is not available for catalog attachment",
        )
    return asset


async def enqueue_abandoned_upload_cleanup(
    db: AsyncSession,
    *,
    now: datetime,
    retention: timedelta,
    retry_after: timedelta,
    batch_size: int,
) -> int:
    candidates = list(
        await db.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.deleted_at.is_(None),
                or_(
                    and_(
                        MediaAsset.status == "pending",
                        MediaAsset.created_at < now - retention,
                    ),
                    and_(
                        MediaAsset.status == "deletion_pending",
                        MediaAsset.updated_at < now - retry_after,
                    ),
                ),
            )
            .order_by(MediaAsset.created_at, MediaAsset.id)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
    )
    for asset in candidates:
        if asset.status == "pending":
            asset.status = "deletion_pending"
            asset.processing_error = "upload authorization expired before completion"
        asset.updated_at = now
        db.add(
            MediaTaskIntent(
                task_name="media.delete_asset.v1",
                payload={"media_asset_id": str(asset.id)},
            )
        )
    if candidates:
        await db.commit()
    return len(candidates)


async def load_cleanup_candidate(db: AsyncSession, *, asset_id: UUID) -> CleanupCandidate | None:
    asset = await db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.status == "deletion_pending",
            MediaAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        return None
    derivatives = list(
        await db.scalars(
            select(MediaDerivative.object_key).where(MediaDerivative.media_asset_id == asset.id)
        )
    )
    return CleanupCandidate(
        asset_id=asset.id,
        object_keys=(asset.original_object_key, *derivatives),
    )


async def finalize_asset_cleanup(db: AsyncSession, *, asset_id: UUID, now: datetime) -> None:
    asset = await db.get(MediaAsset, asset_id, with_for_update=True)
    if asset is None or asset.status != "deletion_pending" or asset.deleted_at is not None:
        return
    await db.execute(delete(MediaDerivative).where(MediaDerivative.media_asset_id == asset.id))
    asset.status = "deleted"
    asset.deleted_at = now
    asset.processing_error = None
    await db.commit()
