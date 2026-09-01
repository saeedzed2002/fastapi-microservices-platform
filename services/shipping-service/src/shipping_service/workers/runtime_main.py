import asyncio
from functools import partial

from platform_observability import run_background_process
from shipping_service.config import get_settings
from shipping_service.db import dispose_engine
from shipping_service.workers.kafka import consume_order_events


async def run() -> None:
    settings = get_settings()
    workers = (partial(consume_order_events, settings),) if settings.kafka_consumer_enabled else ()
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
