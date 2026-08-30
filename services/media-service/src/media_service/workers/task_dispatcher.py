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


async def _dispatch_intent(intent: MediaTaskIntent, *, timeout_seconds: float) -> None:
    targets = {
        "media.process_asset.v1": "media_service.process_asset",
        "media.delete_asset.v1": "media_service.delete_asset",
    }
    task_name = targets.get(intent.task_name)
    if task_name is None:
        raise ValueError(f"unsupported media task intent: {intent.task_name}")
    await asyncio.wait_for(
        asyncio.to_thread(
            celery_app.send_task,
            task_name,
            kwargs=intent.payload,
            queue="media.processing",
        ),
        timeout=timeout_seconds,
    )


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
            await _dispatch_intent(
                intent,
                timeout_seconds=settings.task_dispatcher_publish_timeout_seconds,
            )
            await _mark(intent.id, status="dispatched")
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            await _mark(intent.id, status="pending", error="Celery publish timed out")
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
        except Exception as exc:
            await _mark(intent.id, status="pending", error=str(exc))
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
