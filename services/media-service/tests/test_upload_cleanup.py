import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

from media_service.application import (
    enqueue_abandoned_upload_cleanup,
    finalize_asset_cleanup,
    load_cleanup_candidate,
)
from media_service.models import MediaAsset, MediaTaskIntent


class FakeSession:
    def __init__(
        self, *, asset: MediaAsset | None, scalar_lists: list[list[str]] | None = None
    ) -> None:
        self.asset = asset
        self.scalar_lists = scalar_lists or []
        self.added: list[object] = []
        self.commit = AsyncMock()
        self.execute = AsyncMock()

    async def scalars(self, statement: object) -> list[MediaAsset] | list[str]:
        del statement
        if self.scalar_lists:
            return self.scalar_lists.pop(0)
        return [self.asset] if self.asset is not None else []

    async def scalar(self, statement: object) -> MediaAsset | None:
        del statement
        return self.asset

    async def get(self, model: object, value: object, **kwargs: object) -> MediaAsset | None:
        del model, value, kwargs
        return self.asset

    def add(self, value: object) -> None:
        self.added.append(value)


def _asset(*, status: str = "pending") -> MediaAsset:
    return MediaAsset(
        id=uuid4(),
        owner_subject_id=uuid4(),
        purpose="product_image",
        original_object_key="uploads/test/original",
        content_type="image/jpeg",
        size_bytes=123,
        checksum_sha256="a" * 64,
        status=status,
        created_at=datetime.now(UTC) - timedelta(days=2),
    )


def test_abandoned_pending_upload_becomes_a_durable_delete_intent() -> None:
    async def exercise() -> None:
        asset = _asset()
        session = FakeSession(asset=asset)

        queued = await enqueue_abandoned_upload_cleanup(
            session,  # type: ignore[arg-type]
            now=datetime.now(UTC),
            retention=timedelta(days=1),
            retry_after=timedelta(hours=1),
            batch_size=100,
        )

        assert queued == 1
        assert asset.status == "deletion_pending"
        intent = next(item for item in session.added if isinstance(item, MediaTaskIntent))
        assert intent.task_name == "media.delete_asset.v1"
        assert intent.payload == {"media_asset_id": str(asset.id)}
        session.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_cleanup_deletes_original_and_derivatives_only_after_the_intent_is_claimed() -> None:
    async def exercise() -> None:
        asset = _asset(status="deletion_pending")
        session = FakeSession(asset=asset, scalar_lists=[["derivatives/test/thumbnail.webp"]])

        candidate = await load_cleanup_candidate(session, asset_id=asset.id)  # type: ignore[arg-type]

        assert candidate is not None
        assert candidate.object_keys == (
            "uploads/test/original",
            "derivatives/test/thumbnail.webp",
        )
        await finalize_asset_cleanup(
            session,  # type: ignore[arg-type]
            asset_id=asset.id,
            now=datetime.now(UTC),
        )
        assert asset.status == "deleted"
        assert asset.deleted_at is not None
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    asyncio.run(exercise())
