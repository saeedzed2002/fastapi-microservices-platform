# mypy: disable-error-code=untyped-decorator

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from botocore.exceptions import BotoCoreError  # type: ignore[import-untyped]
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from media_service.application import (
    enqueue_abandoned_upload_cleanup,
    finalize_asset_cleanup,
    load_cleanup_candidate,
)
from media_service.config import get_settings
from media_service.db import dispose_engine, get_session_factory
from media_service.models import MediaAsset, MediaDerivative, OutboxMessage
from media_service.storage import S3ObjectStorage
from media_service.workers.celery_app import celery_app


def _thumbnail(data: bytes) -> tuple[bytes, int, int]:
    with Image.open(BytesIO(data)) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.thumbnail((512, 512))
        output = BytesIO()
        normalized.save(output, format="WEBP", quality=85, method=6)
        return output.getvalue(), normalized.width, normalized.height


async def process_media_asset(media_asset_id: UUID) -> None:
    settings = get_settings()
    storage = S3ObjectStorage(settings)
    async with get_session_factory()() as db:
        asset = await db.get(MediaAsset, media_asset_id)
        if asset is None or asset.status == "ready" or asset.deleted_at is not None:
            return
        if asset.status not in {"uploaded", "processing"}:
            return
        asset.status = "processing"
        await db.commit()
    try:
        source = await asyncio.to_thread(storage.get_bytes, object_key=asset.original_object_key)
        derivative_data, width, height = await asyncio.to_thread(_thumbnail, source)
        derivative_key = f"derivatives/{asset.owner_subject_id}/{asset.id}/thumbnail.webp"
        await asyncio.to_thread(
            storage.put_bytes,
            object_key=derivative_key,
            content_type="image/webp",
            data=derivative_data,
        )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        async with get_session_factory()() as db:
            asset = await db.get(MediaAsset, media_asset_id)
            if asset is not None:
                asset.status = "failed"
                asset.processing_error = str(exc)[:2000]
                await db.commit()
        return
    async with get_session_factory()() as db:
        asset = await db.get(MediaAsset, media_asset_id)
        if asset is None or asset.status == "ready":
            return
        derivative = await db.scalar(
            select(MediaDerivative).where(
                MediaDerivative.media_asset_id == asset.id,
                MediaDerivative.kind == "thumbnail",
            )
        )
        if derivative is None:
            db.add(
                MediaDerivative(
                    media_asset_id=asset.id,
                    kind="thumbnail",
                    object_key=derivative_key,
                    content_type="image/webp",
                    size_bytes=len(derivative_data),
                    checksum_sha256=hashlib.sha256(derivative_data).hexdigest(),
                    width=width,
                    height=height,
                )
            )
        asset.status = "ready"
        asset.ready_at = datetime.now(UTC)
        asset.processing_error = None
        db.add(
            OutboxMessage(
                event_type="media.ready.v1",
                aggregate_type="media_asset",
                aggregate_id=asset.id,
                payload={
                    "media_asset_id": str(asset.id),
                    "purpose": asset.purpose,
                    "content_type": asset.content_type,
                    "derivative_kinds": ["thumbnail"],
                },
                headers={"producer": settings.service_name},
            )
        )
        await db.commit()


async def _process_and_dispose(media_asset_id: UUID) -> None:
    try:
        await process_media_asset(media_asset_id)
    finally:
        await dispose_engine()


@celery_app.task(
    name="media_service.process_asset",
    bind=True,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_asset_task(self: object, *, media_asset_id: str) -> None:
    asyncio.run(_process_and_dispose(UUID(media_asset_id)))


async def delete_media_asset(media_asset_id: UUID) -> None:
    settings = get_settings()
    storage = S3ObjectStorage(settings)
    async with get_session_factory()() as db:
        candidate = await load_cleanup_candidate(db, asset_id=media_asset_id)
    if candidate is None:
        return
    await asyncio.to_thread(storage.delete_objects, object_keys=candidate.object_keys)
    async with get_session_factory()() as db:
        await finalize_asset_cleanup(db, asset_id=candidate.asset_id, now=datetime.now(UTC))


async def _delete_and_dispose(media_asset_id: UUID) -> None:
    try:
        await delete_media_asset(media_asset_id)
    finally:
        await dispose_engine()


@celery_app.task(
    name="media_service.delete_asset",
    bind=True,
    autoretry_for=(BotoCoreError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def delete_asset_task(self: object, *, media_asset_id: str) -> None:
    asyncio.run(_delete_and_dispose(UUID(media_asset_id)))


async def reap_abandoned_uploads() -> int:
    settings = get_settings()
    if not settings.abandoned_upload_cleanup_enabled:
        return 0
    async with get_session_factory()() as db:
        return await enqueue_abandoned_upload_cleanup(
            db,
            now=datetime.now(UTC),
            retention=timedelta(seconds=settings.abandoned_upload_retention_seconds),
            retry_after=timedelta(seconds=settings.abandoned_upload_reap_interval_seconds),
            batch_size=settings.abandoned_upload_cleanup_batch_size,
        )


async def _reap_and_dispose() -> int:
    try:
        return await reap_abandoned_uploads()
    finally:
        await dispose_engine()


@celery_app.task(name="media_service.reap_abandoned_uploads")
def reap_abandoned_uploads_task() -> int:
    return asyncio.run(_reap_and_dispose())
