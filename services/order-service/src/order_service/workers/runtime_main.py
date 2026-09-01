import asyncio
from functools import partial

from order_service.config import get_settings
from order_service.db import dispose_engine
from order_service.workers.kafka import (
    consume_invoice_events,
    consume_saga_events,
    consume_shipping_events,
    publish_outbox,
)
from order_service.workers.task_dispatcher import run_task_dispatcher
from platform_observability import run_background_process


async def run() -> None:
    settings = get_settings()
    workers = tuple(
        worker
        for enabled, worker in (
            (settings.kafka_publisher_enabled, partial(publish_outbox, settings)),
            (settings.kafka_consumer_enabled, partial(consume_saga_events, settings)),
            (settings.invoice_consumer_enabled, partial(consume_invoice_events, settings)),
            (settings.shipping_consumer_enabled, partial(consume_shipping_events, settings)),
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
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
