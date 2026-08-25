import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from notification_service.application import accept_invoice_generated
from notification_service.config import Settings
from notification_service.db import get_session_factory
from platform_messaging import KafkaDlqPolicy, process_record_with_dead_letter


async def consume_invoice_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_invoice_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="notification-service",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers, enable_idempotence=True
    )
    await consumer.start()
    await producer.start()
    try:
        async for message in consumer:

            async def handle(current_message: Any = message) -> None:
                message_value = current_message.value
                envelope = json.loads(message_value)
                if envelope.get("event_type") == "invoice.generated.v1":
                    async with get_session_factory()() as db:
                        await accept_invoice_generated(db, envelope)

            await process_record_with_dead_letter(
                consumer=consumer,
                producer=producer,
                record=message,
                policy=KafkaDlqPolicy(
                    consumer_name="notification-service.invoice",
                    dead_letter_topic=settings.kafka_dead_letter_topic,
                    max_attempts=settings.kafka_consumer_max_attempts,
                    retry_backoff_seconds=settings.kafka_consumer_retry_backoff_seconds,
                ),
                handler=handle,
                stop=stop,
            )
            if stop.is_set():
                break
    finally:
        await producer.stop()
        await consumer.stop()
