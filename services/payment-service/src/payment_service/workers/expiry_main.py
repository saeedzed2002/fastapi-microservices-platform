import asyncio
import signal

from payment_service.config import get_settings
from payment_service.db import dispose_engine
from payment_service.workers.expiry import expire_payment_intents


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, stop.set)
    try:
        await expire_payment_intents(get_settings(), stop)
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
