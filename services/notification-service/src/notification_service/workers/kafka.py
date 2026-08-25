import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

from notification_service.application import accept_invoice_generated
from notification_service.config import Settings
from notification_service.db import get_session_factory

logger = logging.getLogger(__name__)


async def consume_invoice_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_invoice_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="notification-service",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                envelope = json.loads(message.value)
                if envelope.get("event_type") == "invoice.generated.v1":
                    async with get_session_factory()() as db:
                        await accept_invoice_generated(db, envelope)
                await consumer.commit()
            except Exception:
                logger.exception("notification_invoice_consume_failed")
            if stop.is_set():
                break
    finally:
        await consumer.stop()
