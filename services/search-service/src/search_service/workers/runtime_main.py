import asyncio
from functools import partial

from platform_observability import run_background_process
from search_service.config import get_settings
from search_service.db import dispose_engine
from search_service.workers.kafka import consume_catalog_events


async def run() -> None:
    settings = get_settings()
    workers = (
        (partial(consume_catalog_events, settings),) if settings.kafka_consumer_enabled else ()
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
