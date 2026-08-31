import asyncio
from functools import partial

from inventory_service.config import get_settings
from inventory_service.db import dispose_engine
from inventory_service.workers.kafka import consume_saga_events, publish_outbox
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = tuple(
        worker
        for enabled, worker in (
            (settings.kafka_publisher_enabled, partial(publish_outbox, settings)),
            (settings.kafka_consumer_enabled, partial(consume_saga_events, settings)),
        )
        if enabled
    )
    await run_background_process(
        service_name=settings.service_name,
        service_version=settings.service_version,
        environment=settings.environment,
        workers=workers,
        shutdown=dispose_engine,
        log_level=settings.log_level,
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
