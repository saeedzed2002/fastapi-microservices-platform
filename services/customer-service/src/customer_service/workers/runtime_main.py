import asyncio
from functools import partial

from customer_service.config import get_settings
from customer_service.db import dispose_engine
from customer_service.workers.identity_consumer import consume_identity_events
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = (
        (partial(consume_identity_events, settings),) if settings.kafka_consumer_enabled else ()
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
