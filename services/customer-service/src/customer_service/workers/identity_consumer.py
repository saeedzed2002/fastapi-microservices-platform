import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from customer_service.application import provision_identity_customer
from customer_service.config import Settings
from customer_service.db import get_session_factory
from platform_messaging import KafkaDlqPolicy, process_record_with_dead_letter


async def handle_identity_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type not in {"identity.user_registered.v1", "identity.user_registered.v2"}:
        return
    event_payload = payload.get("payload", {})
    event_id = payload.get("event_id")
    user_id = event_payload.get("user_id")
    email = event_payload.get("email")
    phone = event_payload.get("phone")
    if (
        not isinstance(event_id, str)
        or not isinstance(user_id, str)
        or not isinstance(event_type, str)
        or (email is not None and not isinstance(email, str))
        or (phone is not None and not isinstance(phone, str))
        or (email is None and phone is None)
    ):
        raise ValueError("identity user registration event has invalid payload")
    from uuid import UUID

    async with get_session_factory()() as db:
        await provision_identity_customer(
            db,
            event_id=UUID(event_id),
            event_type=event_type,
            user_id=UUID(user_id),
            email=email,
            phone=phone,
        )
        await db.commit()


async def consume_identity_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="customer-service",
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
                await handle_identity_event(json.loads(current_message.value))

            await process_record_with_dead_letter(
                consumer=consumer,
                producer=producer,
                record=message,
                policy=KafkaDlqPolicy(
                    consumer_name="customer-service.identity-projection",
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
