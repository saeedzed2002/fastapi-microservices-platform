import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from media_service.config import Settings
from media_service.db import get_session_factory
from media_service.models import MediaTaskIntent
from media_service.workers.celery_app import celery_app


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _claim_intent() -> MediaTaskIntent | None:
    async with get_session_factory()() as db:
        intent = await db.scalar(
            select(MediaTaskIntent)
            .where(MediaTaskIntent.status == "pending")
            .order_by(MediaTaskIntent.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if intent is None:
            return None
        intent.status = "dispatching"
        intent.attempts += 1
        await db.commit()
        return intent


async def _mark(intent_id: UUID, *, status: str, error: str | None = None) -> None:
    async with get_session_factory()() as db:
        intent = await db.get(MediaTaskIntent, intent_id)
        if intent is None or intent.status != "dispatching":
            return
        intent.status = status
        intent.last_error = error[:2000] if error else None
        intent.dispatched_at = datetime.now(UTC) if status == "dispatched" else None
        await db.commit()


async def run_task_dispatcher(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        intent = await _claim_intent()
        if intent is None:
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
            continue
        try:
            await asyncio.to_thread(
                celery_app.send_task,
                "media_service.process_asset",
                kwargs={"media_asset_id": intent.payload["media_asset_id"]},
                queue="media.processing",
            )
            await _mark(intent.id, status="dispatched")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await _mark(intent.id, status="pending", error=str(exc))
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
