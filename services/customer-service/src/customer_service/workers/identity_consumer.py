import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

from customer_service.application import provision_customer
from customer_service.config import Settings
from customer_service.db import get_session_factory

logger = logging.getLogger(__name__)


async def handle_identity_event(payload: dict[str, Any]) -> None:
    if payload.get("event_type") != "identity.user_registered.v1":
        return
    event_payload = payload.get("payload", {})
    user_id = event_payload.get("user_id")
    email = event_payload.get("email")
    if not isinstance(user_id, str) or not isinstance(email, str):
        raise ValueError("identity.user_registered.v1 has invalid payload")
    from uuid import UUID

    async with get_session_factory()() as db:
        await provision_customer(db, user_id=UUID(user_id), email=email)
        await db.commit()


async def consume_identity_events(settings: Settings, stop: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="customer-service",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                await handle_identity_event(json.loads(message.value))
                await consumer.commit()
            except Exception:
                logger.exception("identity_event_failed")
            if stop.is_set():
                break
    finally:
        await consumer.stop()
