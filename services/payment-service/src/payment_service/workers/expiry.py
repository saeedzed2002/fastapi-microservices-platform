import asyncio
import logging
from contextlib import suppress

from payment_service.application import expire_due_payment_intents
from payment_service.config import Settings
from payment_service.db import get_session_factory

logger = logging.getLogger(__name__)


async def expire_payment_intents(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with get_session_factory()() as db:
                expired = await expire_due_payment_intents(db)
                if expired:
                    logger.info("payment_intents_expired", extra={"count": expired})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("payment_intent_expiry_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.expiry_poll_interval_seconds)
