import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.application import (
    PaymentExpired,
    PaymentIntentNotFound,
    PaymentNotReady,
    PaymentRequestInProgress,
    UnsupportedPaymentCurrency,
    handle_zarinpal_callback,
    start_zarinpal_payment,
)
from payment_service.auth import bearer, require_customer
from payment_service.config import get_settings
from payment_service.db import dispose_engine, get_session
from payment_service.order_gateway import (
    OrderGatewayUnavailable,
    OrderNotPayable,
    ensure_customer_can_pay_order,
)
from payment_service.schemas import ZarinpalCallbackResponse, ZarinpalStartResponse
from payment_service.workers.expiry import expire_payment_intents
from payment_service.workers.kafka import consume_reservation_events, publish_outbox
from payment_service.zarinpal import (
    ZarinpalClient,
    ZarinpalNotConfigured,
    ZarinpalRejected,
    ZarinpalUnavailable,
)
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_publisher_enabled:
        tasks.append(asyncio.create_task(publish_outbox(settings, stop)))
    if settings.kafka_consumer_enabled:
        tasks.append(asyncio.create_task(consume_reservation_events(settings, stop)))
    if settings.expiry_worker_enabled:
        tasks.append(asyncio.create_task(expire_payment_intents(settings, stop)))
    logger.info("service_started")
    yield
    stop.set()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Payment Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


def zarinpal_client() -> ZarinpalClient:
    return ZarinpalClient(
        merchant_id=settings.zarinpal_merchant_id,
        sandbox=settings.zarinpal_sandbox,
        callback_url=settings.zarinpal_callback_url,
        timeout_seconds=settings.zarinpal_request_timeout_seconds,
    )


@app.post(
    "/api/v1/payments/orders/{order_id}/zarinpal",
    response_model=ZarinpalStartResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required or invalid"},
        status.HTTP_403_FORBIDDEN: {"description": "Customer role required"},
        status.HTTP_409_CONFLICT: {"description": "Payment is not ready or is unavailable"},
        status.HTTP_502_BAD_GATEWAY: {"description": "Payment provider rejected the request"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Order lookup or payment provider is unavailable"
        },
    },
)
async def start_zarinpal(
    order_id: UUID,
    _: AuthClaims = Depends(require_customer),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> ZarinpalStartResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        await ensure_customer_can_pay_order(
            base_url=settings.order_base_url,
            timeout_seconds=settings.order_request_timeout_seconds,
            order_id=order_id,
            access_token=credentials.credentials,
        )
        result = await start_zarinpal_payment(
            db,
            order_id=order_id,
            provider=zarinpal_client(),
            expected_currency=settings.zarinpal_currency,
        )
    except OrderGatewayUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="order lookup unavailable"
        ) from exc
    except OrderNotPayable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment not ready"
        ) from exc
    except PaymentIntentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment not ready"
        ) from exc
    except (PaymentNotReady, PaymentRequestInProgress) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment not ready"
        ) from exc
    except (PaymentExpired, UnsupportedPaymentCurrency) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment unavailable"
        ) from exc
    except (ZarinpalNotConfigured, ZarinpalUnavailable) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="payment provider unavailable"
        ) from exc
    except ZarinpalRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="payment provider rejected request"
        ) from exc
    return ZarinpalStartResponse.model_validate(result)


@app.get(
    "/api/v1/payments/zarinpal/callback",
    response_model=ZarinpalCallbackResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Payment authority was not found"},
        status.HTTP_409_CONFLICT: {"description": "Payment is not ready for verification"},
        status.HTTP_502_BAD_GATEWAY: {"description": "Payment provider rejected verification"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Payment provider is unavailable"},
    },
)
async def zarinpal_callback(
    authority: str = Query(alias="Authority", min_length=1, max_length=64),
    provider_status: str = Query(alias="Status", min_length=1, max_length=32),
    db: AsyncSession = Depends(get_session),
) -> ZarinpalCallbackResponse:
    try:
        result = await handle_zarinpal_callback(
            db,
            provider=zarinpal_client(),
            authority=authority,
            provider_status=provider_status,
        )
    except PaymentIntentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="payment not found"
        ) from exc
    except (PaymentNotReady, PaymentRequestInProgress) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment not ready"
        ) from exc
    except (ZarinpalNotConfigured, ZarinpalUnavailable) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="payment provider unavailable"
        ) from exc
    except ZarinpalRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="payment provider rejected request"
        ) from exc
    return ZarinpalCallbackResponse.model_validate(result)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return (
        "# HELP payment_service_up Service availability\n"
        "# TYPE payment_service_up gauge\n"
        "payment_service_up 1\n"
    )
