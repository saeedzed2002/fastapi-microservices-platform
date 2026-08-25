import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select

from media_service.config import Settings
from media_service.db import get_session_factory
from media_service.models import MediaTaskIntent
from media_service.workers.celery_app import celery_app


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _next_intent() -> MediaTaskIntent | None:
    async with get_session_factory()() as db:
        return cast(
            MediaTaskIntent | None,
            await db.scalar(
                select(MediaTaskIntent)
                .where(MediaTaskIntent.status == "pending")
                .order_by(MediaTaskIntent.created_at)
                .limit(1)
            ),
        )


async def _mark_dispatched(intent_id: object) -> None:
    async with get_session_factory()() as db:
        intent = await db.get(MediaTaskIntent, intent_id)
        if intent is not None and intent.status == "pending":
            intent.status = "dispatched"
            intent.dispatched_at = datetime.now(UTC)
            await db.commit()


async def _record_failure(intent_id: object, error: str) -> None:
    async with get_session_factory()() as db:
        intent = await db.get(MediaTaskIntent, intent_id)
        if intent is not None and intent.status == "pending":
            intent.attempts += 1
            intent.last_error = error[:2000]
            await db.commit()


async def run_task_dispatcher(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        intent = await _next_intent()
        if intent is None:
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
            continue
        try:
            await asyncio.to_thread(
                celery_app.send_task,
                "media_service.process_asset",
                kwargs={"media_asset_id": intent.payload["media_asset_id"]},
            )
            await _mark_dispatched(intent.id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await _record_failure(intent.id, str(exc))
            await _wait(stop, settings.task_dispatcher_poll_interval_seconds)
