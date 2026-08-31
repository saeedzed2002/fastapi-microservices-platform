import asyncio
import signal

from payment_service.config import get_settings
from payment_service.db import dispose_engine
from payment_service.workers.expiry import expire_payment_intents
from platform_observability import configure_runtime


async def run() -> None:
    settings = get_settings()
    configure_runtime(
        service_name=settings.service_name,
        service_version=settings.service_version,
        environment=settings.environment,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, stop.set)
    try:
        await expire_payment_intents(settings, stop)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
