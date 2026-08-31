import asyncio
from functools import partial

from catalog_service.config import get_settings
from catalog_service.db import dispose_engine
from catalog_service.workers.kafka import publish_outbox
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = (partial(publish_outbox, settings),) if settings.kafka_publisher_enabled else ()
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
