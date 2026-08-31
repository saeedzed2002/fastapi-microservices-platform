import asyncio
from functools import partial

from media_service.config import get_settings
from media_service.db import dispose_engine
from media_service.workers.outbox_publisher import run_outbox_publisher
from media_service.workers.task_dispatcher import run_task_dispatcher
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = tuple(
        worker
        for enabled, worker in (
            (settings.kafka_publisher_enabled, partial(run_outbox_publisher, settings)),
            (settings.task_dispatcher_enabled, partial(run_task_dispatcher, settings)),
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
