import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]
from sqlalchemy import or_, select

from payment_service.application import process_reservation_event
from payment_service.config import Settings
from payment_service.db import get_session_factory
from payment_service.models import OutboxMessage

logger = logging.getLogger(__name__)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _claim_outbox(
    settings: Settings,
) -> tuple[UUID, UUID, dict[str, Any]] | None:
    claim_expiry = datetime.now(UTC) - timedelta(seconds=settings.outbox_claim_lease_seconds)
    async with get_session_factory()() as db:
        message = await db.scalar(
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
        )
        if message is None:
            return None
        claim_token = uuid4()
        message.publish_claim_token = claim_token
        message.publish_claimed_at = datetime.now(UTC)
        message.attempts += 1
        envelope = {
            "event_id": str(message.event_id),
            "event_type": message.event_type,
            "event_version": 1,
            "aggregate_type": message.aggregate_type,
            "aggregate_id": str(message.aggregate_id),
            "producer": settings.service_name,
            "occurred_at": message.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "correlation_id": str(message.correlation_id),
            "causation_id": str(message.causation_id) if message.causation_id else None,
            "trace_id": message.trace_id,
            "payload": message.payload,
        }
        await db.commit()
        return message.id, claim_token, envelope


async def _finish_outbox_claim(
    message_id: UUID, claim_token: UUID, *, published: bool, error: str | None = None
) -> None:
    async with get_session_factory()() as db:
        message = await db.get(OutboxMessage, message_id, with_for_update=True)
        if message is None or message.publish_claim_token != claim_token:
            return
        if published:
            message.published_at = datetime.now(UTC)
            message.last_error = None
        else:
            message.last_error = (error or "Kafka publication failed")[:2000]
        message.publish_claim_token = None
        message.publish_claimed_at = None
        await db.commit()


async def publish_outbox(settings: Settings, stop: asyncio.Event) -> None:
    producer: Any | None = None
    try:
        while not stop.is_set():
            try:
                if producer is None:
                    producer = AIOKafkaProducer(
                        bootstrap_servers=settings.kafka_bootstrap_servers, enable_idempotence=True
                    )
                    await producer.start()
                claim = await _claim_outbox(settings)
                if claim is None:
                    await _wait(stop, settings.outbox_poll_interval_seconds)
                    continue
                message_id, claim_token, envelope = claim
                try:
                    await producer.send_and_wait(
                        settings.kafka_topic,
                        key=envelope["aggregate_id"].encode(),
                        value=json.dumps(envelope, separators=(",", ":")).encode(),
                    )
                except Exception as exc:
                    await _finish_outbox_claim(
                        message_id, claim_token, published=False, error=str(exc)
                    )
                    raise
                await _finish_outbox_claim(message_id, claim_token, published=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("payment_outbox_publish_failed")
                if producer is not None:
                    with suppress(Exception):
                        await producer.stop()
                    producer = None
                await _wait(stop, 1)
    finally:
        if producer is not None:
            await producer.stop()


async def consume_reservation_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_reservation_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="payment-service",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                payload = json.loads(message.value)
                if payload.get("event_type") == "inventory.reserved.v1":
                    async with get_session_factory()() as db:
                        await process_reservation_event(db, payload)
                await consumer.commit()
            except Exception:
                logger.exception("payment_reservation_consume_failed")
            if stop.is_set():
                break
    finally:
        await consumer.stop()
