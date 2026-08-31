import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from notification_service.application import accept_otp_sms_delivery
from notification_service.config import get_settings
from notification_service.db import dispose_engine, get_session
from notification_service.schemas import OtpSmsDeliveryRequest, OtpSmsDeliveryResponse
from notification_service.workers.kafka import consume_invoice_events
from notification_service.workers.task_dispatcher import run_task_dispatcher
from platform_observability import configure_application, metrics_response

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_consumer_enabled:
        tasks.append(asyncio.create_task(consume_invoice_events(settings, stop)))
    if settings.task_dispatcher_enabled:
        tasks.append(asyncio.create_task(run_task_dispatcher(settings, stop)))
    logger.info("service_started")
    yield
    stop.set()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Notification Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
)


def require_internal_otp_token(token: str | None) -> None:
    expected = settings.internal_otp_shared_secret
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal OTP delivery is not configured",
        )
    if token is None or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="internal authentication required"
        )


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post(
    "/internal/v1/otp-deliveries",
    response_model=OtpSmsDeliveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def enqueue_otp_delivery(
    payload: OtpSmsDeliveryRequest,
    internal_token: str | None = Header(default=None, alias="X-Platform-Internal-Token"),
    db: AsyncSession = Depends(get_session),
) -> OtpSmsDeliveryResponse:
    require_internal_otp_token(internal_token)
    if not settings.smsir_enabled or not settings.smsir_api_key or not settings.smsir_line_number:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS OTP delivery is not configured",
        )
    delivery = await accept_otp_sms_delivery(
        db,
        delivery_id=payload.delivery_id,
        phone=payload.phone,
    )
    return OtpSmsDeliveryResponse(delivery_id=delivery.id)


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()
