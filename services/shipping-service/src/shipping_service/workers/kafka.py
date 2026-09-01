import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from platform_messaging import KafkaDlqPolicy, process_record_with_dead_letter
from shipping_service.application import process_order_event
from shipping_service.config import Settings
from shipping_service.db import get_session_factory


async def consume_order_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_order_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
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
                envelope = json.loads(current_message.value)
                async with get_session_factory()() as db:
                    await process_order_event(db, envelope)

            await process_record_with_dead_letter(
                consumer=consumer,
                producer=producer,
                record=message,
                policy=KafkaDlqPolicy(
                    consumer_name="shipping-service.order",
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
