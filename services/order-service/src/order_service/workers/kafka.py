import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]
from sqlalchemy import select

from order_service.application import process_saga_result
from order_service.config import Settings
from order_service.db import get_session_factory
from order_service.invoice_application import accept_invoice_request
from order_service.models import OutboxMessage

logger = logging.getLogger(__name__)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def publish_outbox(settings: Settings, stop: asyncio.Event) -> None:
    producer: Any | None = None
    try:
        while not stop.is_set():
            try:
                if producer is None:
                    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
                    await producer.start()
                async with get_session_factory()() as db:
                    message = await db.scalar(
                        select(OutboxMessage)
                        .where(OutboxMessage.published_at.is_(None))
                        .order_by(OutboxMessage.occurred_at)
                        .limit(1)
                    )
                    if message is None:
                        await _wait(stop, settings.outbox_poll_interval_seconds)
                        continue
                    envelope = {
                        "event_id": str(message.event_id),
                        "event_type": message.event_type,
                        "event_version": 1,
                        "aggregate_type": message.aggregate_type,
                        "aggregate_id": str(message.aggregate_id),
                        "producer": settings.service_name,
                        "occurred_at": message.occurred_at.astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "correlation_id": str(message.correlation_id),
                        "causation_id": str(message.causation_id) if message.causation_id else None,
                        "trace_id": message.trace_id,
                        "payload": message.payload,
                    }
                    await producer.send_and_wait(
                        settings.kafka_topic,
                        key=str(message.correlation_id).encode(),
                        value=json.dumps(envelope).encode(),
                    )
                    message.published_at = datetime.now(UTC)
                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("order_outbox_publish_failed")
                if producer is not None:
                    with suppress(Exception):
                        await producer.stop()
                    producer = None
                await _wait(stop, 1)
    finally:
        if producer is not None:
            await producer.stop()


async def consume_saga_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        "fastapi-platform.inventory.events.v1",
        "fastapi-platform.payment.events.v1",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="order-service",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                async with get_session_factory()() as db:
                    await process_saga_result(db, json.loads(message.value))
                await consumer.commit()
            except Exception:
                logger.exception("order_saga_consume_failed")
            if stop.is_set():
                break
    finally:
        await consumer.stop()


async def consume_invoice_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="order-invoice-dispatcher",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                envelope = json.loads(message.value)
                if envelope.get("event_type") == "order.confirmed.v1":
                    async with get_session_factory()() as db:
                        await accept_invoice_request(db, envelope)
                await consumer.commit()
            except Exception:
                logger.exception("order_invoice_consume_failed")
            if stop.is_set():
                break
    finally:
        await consumer.stop()
