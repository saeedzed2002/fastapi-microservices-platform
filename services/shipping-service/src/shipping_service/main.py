import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_auth import AuthClaims
from platform_observability import configure_application, metrics_response
from shipping_service.application import (
    commit_status_transition,
    load_command_recovery,
    load_idempotent_status_transition,
)
from shipping_service.auth import bearer, require_administrator
from shipping_service.config import get_settings
from shipping_service.db import dispose_engine, get_session
from shipping_service.order_access import verify_order_recovery_proof
from shipping_service.order_gateway import (
    HttpOrderAuthorizationGateway,
    OrderAuthorizationUnavailable,
)
from shipping_service.schemas import (
    ShipmentStatusResponse,
    ShipmentStatusUpdateRequest,
    ShippingCommandRecoveryResponse,
)

settings = get_settings()
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.order_authorization_gateway = HttpOrderAuthorizationGateway(settings)
    logger.info("service_started")
    yield
    await application.state.order_authorization_gateway.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Shipping Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
    log_level=settings.log_level,
)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()


@app.put(
    "/api/v1/shipping/admin/orders/{order_id}/status",
    response_model=ShipmentStatusResponse,
)
async def update_administrator_shipment_status(
    order_id: UUID,
    payload: ShipmentStatusUpdateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_administrator),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> ShipmentStatusResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    command_id = uuid5(NAMESPACE_URL, f"shipping-status:{order_id}:{idempotency_key}")
    existing = await load_idempotent_status_transition(
        db,
        order_id=order_id,
        command_id=command_id,
        requested_by=claims.subject,
        payload=payload,
    )
    if existing is not None:
        return existing
    gateway: HttpOrderAuthorizationGateway = app.state.order_authorization_gateway
    try:
        authorization = await gateway.authorize(
            order_id=order_id,
            command_id=command_id,
            target_status=payload.status,
            access_token=credentials.credentials,
        )
    except OrderAuthorizationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "order authorization outcome is unavailable; retry with the same idempotency key"
            ),
        ) from exc
    if (
        authorization.order_id != order_id
        or authorization.command_id != command_id
        or authorization.target_status != payload.status
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="order authorization returned an invalid result",
        )
    return await commit_status_transition(
        db,
        order_id=order_id,
        command_id=command_id,
        authorization_id=authorization.authorization_id,
        requested_by=claims.subject,
        authorization_expires_at=authorization.expires_at,
        payload=payload,
    )


@app.get(
    "/api/internal/v1/shipping/commands/{command_id}",
    response_model=ShippingCommandRecoveryResponse,
    include_in_schema=False,
)
async def get_shipping_command_recovery(
    command_id: UUID,
    proof_expires_at: int = Query(ge=1),
    order_access_proof: str = Header(alias="X-Order-Shipping-Proof", min_length=64, max_length=64),
    db: AsyncSession = Depends(get_session),
) -> ShippingCommandRecoveryResponse:
    verify_order_recovery_proof(
        settings=settings,
        provided_proof=order_access_proof,
        command_id=command_id,
        expires_at=proof_expires_at,
    )
    return await load_command_recovery(db, command_id=command_id)
