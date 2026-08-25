import asyncio
import json
import logging
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from sqlalchemy import or_, select

from identity_service.config import Settings
from identity_service.db import get_session_factory
from identity_service.models import OutboxMessage

logger = logging.getLogger(__name__)
_EVENT_VERSION = re.compile(r"\.v([1-9][0-9]*)$")


def build_event_envelope(message: OutboxMessage, *, producer: str) -> dict[str, Any]:
    match = _EVENT_VERSION.search(message.event_type)
    if match is None:
        raise ValueError(f"event type is missing a version suffix: {message.event_type}")
    occurred_at = message.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return {
        "event_id": str(message.event_id),
        "event_type": message.event_type,
        "event_version": int(match.group(1)),
        "aggregate_type": message.aggregate_type,
        "aggregate_id": str(message.aggregate_id),
        "producer": producer,
        "occurred_at": occurred_at,
        "correlation_id": str(message.correlation_id),
        "causation_id": str(message.causation_id) if message.causation_id else None,
        "trace_id": message.trace_id,
        "payload": message.payload,
    }


async def _claim_pending(settings: Settings) -> OutboxMessage | None:
    claim_expiry = datetime.now(UTC) - timedelta(seconds=settings.outbox_claim_lease_seconds)
    async with get_session_factory()() as db:
        message = cast(
            OutboxMessage | None,
            await db.scalar(
                select(OutboxMessage)
                .where(
                    OutboxMessage.published_at.is_(None),
                    or_(
                        OutboxMessage.publish_claimed_at.is_(None),
                        OutboxMessage.publish_claimed_at < claim_expiry,
                    ),
                )
                .order_by(OutboxMessage.occurred_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            ),
        )
        if message is None:
            return None
        message.publish_claim_token = uuid4()
        message.publish_claimed_at = datetime.now(UTC)
        message.attempts += 1
        await db.commit()
        return message


async def _mark_published(message_id: UUID, claim_token: UUID) -> None:
    async with get_session_factory()() as db:
        message = await db.get(OutboxMessage, message_id, with_for_update=True)
        if (
            message is not None
            and message.published_at is None
            and message.publish_claim_token == claim_token
        ):
            message.published_at = datetime.now(UTC)
            message.publish_claim_token = None
            message.publish_claimed_at = None
            message.last_error = None
            await db.commit()


async def _record_failure(message_id: UUID, claim_token: UUID, error: str) -> None:
    async with get_session_factory()() as db:
        message = await db.get(OutboxMessage, message_id, with_for_update=True)
        if (
            message is not None
            and message.published_at is None
            and message.publish_claim_token == claim_token
        ):
            message.last_error = error[:2000]
            message.publish_claim_token = None
            message.publish_claimed_at = None
            await db.commit()


async def _wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def run_outbox_publisher(settings: Settings, stop: asyncio.Event) -> None:
    producer: Any | None = None
    message: OutboxMessage | None = None
    try:
        while not stop.is_set():
            try:
                if producer is None:
                    producer = AIOKafkaProducer(
                        bootstrap_servers=settings.kafka_bootstrap_servers,
                        enable_idempotence=True,
                    )
                    await producer.start()

                message = await _claim_pending(settings)
                if message is None:
                    await _wait_or_stop(stop, settings.outbox_poll_interval_seconds)
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
                if message.publish_claim_token is None:
                    raise RuntimeError("claimed outbox message has no claim token")
                await _mark_published(message.id, message.publish_claim_token)
                message = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if message is not None:
                    with suppress(Exception):
                        if message.publish_claim_token is not None:
                            await _record_failure(message.id, message.publish_claim_token, str(exc))
                logger.exception("outbox_publish_failed")
                if producer is not None:
                    with suppress(Exception):
                        await producer.stop()
                    producer = None
                await _wait_or_stop(stop, min(settings.outbox_poll_interval_seconds * 2, 10.0))
    finally:
        if producer is not None:
            with suppress(Exception):
                await producer.stop()
