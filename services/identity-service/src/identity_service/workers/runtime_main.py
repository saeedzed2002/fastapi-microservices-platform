import asyncio
from functools import partial

from identity_service.config import get_settings
from identity_service.db import dispose_engine
from identity_service.workers.outbox_publisher import run_outbox_publisher
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = (partial(run_outbox_publisher, settings),) if settings.kafka_publisher_enabled else ()
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
