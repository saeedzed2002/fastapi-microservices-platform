import asyncio
import json
import re
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast

from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from sqlalchemy import select

from media_service.config import Settings
from media_service.db import get_session_factory
from media_service.models import OutboxMessage

_EVENT_VERSION = re.compile(r"\.v([1-9][0-9]*)$")


def build_event_envelope(message: OutboxMessage, *, producer: str) -> dict[str, Any]:
    match = _EVENT_VERSION.search(message.event_type)
    if match is None:
        raise ValueError(f"event type is missing a version suffix: {message.event_type}")
    return {
        "event_id": str(message.event_id),
        "event_type": message.event_type,
        "event_version": int(match.group(1)),
        "aggregate_type": message.aggregate_type,
        "aggregate_id": str(message.aggregate_id),
        "producer": producer,
        "occurred_at": message.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "correlation_id": str(message.correlation_id),
        "causation_id": str(message.causation_id) if message.causation_id else None,
        "trace_id": message.trace_id,
        "payload": message.payload,
    }


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _next_pending() -> OutboxMessage | None:
    async with get_session_factory()() as db:
        return cast(
            OutboxMessage | None,
            await db.scalar(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.occurred_at)
                .limit(1)
            ),
        )


async def _mark_published(message_id: object) -> None:
    async with get_session_factory()() as db:
        message = await db.get(OutboxMessage, message_id)
        if message is not None and message.published_at is None:
            message.published_at = datetime.now(UTC)
            await db.commit()


async def _record_failure(message_id: object, error: str) -> None:
    async with get_session_factory()() as db:
        message = await db.get(OutboxMessage, message_id)
        if message is not None and message.published_at is None:
            message.attempts += 1
            message.last_error = error[:2000]
            await db.commit()


async def run_outbox_publisher(settings: Settings, stop: asyncio.Event) -> None:
    producer: Any | None = None
    while not stop.is_set():
        message: OutboxMessage | None = None
        try:
            if producer is None:
                producer = AIOKafkaProducer(
                    bootstrap_servers=settings.kafka_bootstrap_servers, enable_idempotence=True
                )
                await producer.start()
            message = await _next_pending()
            if message is None:
                await _wait(stop, settings.outbox_poll_interval_seconds)
                continue
            envelope = build_event_envelope(message, producer=settings.service_name)
            headers = [(key, value.encode("utf-8")) for key, value in message.headers.items()]
            headers.append(("event-id", str(message.event_id).encode("utf-8")))
            await producer.send_and_wait(
                settings.kafka_topic,
                key=str(message.aggregate_id).encode("utf-8"),
                value=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
                headers=headers,
            )
            await _mark_published(message.id)
        except asyncio.CancelledError:
            raise
        except Exception:
            if message is not None:
                with suppress(Exception):
                    await _record_failure(message.id, "Kafka publication failed")
            if producer is not None:
                with suppress(Exception):
                    await producer.stop()
                producer = None
            await _wait(stop, min(settings.outbox_poll_interval_seconds * 2, 10.0))
    if producer is not None:
        with suppress(Exception):
            await producer.stop()
