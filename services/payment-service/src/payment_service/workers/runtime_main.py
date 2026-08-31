import asyncio
from functools import partial

from payment_service.config import get_settings
from payment_service.db import dispose_engine
from payment_service.workers.kafka import consume_reservation_events, publish_outbox
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = tuple(
        worker
        for enabled, worker in (
            (settings.kafka_publisher_enabled, partial(publish_outbox, settings)),
            (settings.kafka_consumer_enabled, partial(consume_reservation_events, settings)),
        )
        if enabled
    )
    await run_background_process(
        service_name=settings.service_name,
        service_version=settings.service_version,
        environment=settings.environment,
        workers=workers,
        shutdown=dispose_engine,
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
