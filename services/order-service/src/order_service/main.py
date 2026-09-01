import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from order_service.application import (
    admin_order_response,
    authorize_fulfillment_transition,
    collect_checkout_snapshot,
    create_order,
    decide_order_return,
    list_administrator_orders,
    list_administrator_returns,
    list_customer_orders,
    load_idempotent_order,
    load_order_or_404,
    load_owned_order_or_404,
    order_response,
    receive_order_return,
    request_order_refund,
    request_order_return,
    validate_checkout_payment,
    wait_for_payment_pending,
)
from order_service.auth import bearer, require_administrator, require_customer
from order_service.cart_gateway import (
    CartGatewayUnavailable,
    EmptyCart,
    consume_cart_checkout_snapshot,
    fetch_cart_checkout_snapshot,
)
from order_service.config import get_settings
from order_service.db import dispose_engine, get_session, get_session_factory
from order_service.payment_gateway import (
    PaymentGatewayUnavailable,
    PaymentNotReady,
    PaymentProviderNotConfigured,
    PaymentProviderRejected,
    start_online_checkout,
    start_zarinpal_checkout,
)
from order_service.schemas import (
    AdminOrderPage,
    AdminOrderResponse,
    CartCheckoutRequest,
    CartCheckoutResponse,
    CheckoutRequest,
    CustomerOrderPage,
    FulfillmentAuthorizationRequest,
    FulfillmentAuthorizationResponse,
    FulfillmentCommandResponse,
    FulfillmentStatus,
    FulfillmentUpdateRequest,
    OrderResponse,
    OrderStatus,
    RefundRequestResponse,
    ReturnDecisionRequest,
    ReturnRequestCreate,
    ReturnRequestPage,
    ReturnRequestResponse,
    ReturnStatus,
)
from order_service.shipping_access import verify_shipping_authorization_proof
from order_service.shipping_gateway import (
    HttpShippingRecoveryGateway,
    ShippingCommandUnavailable,
    ShippingRecoveryUnavailable,
)
from order_service.workers.kafka import consume_invoice_events, consume_saga_events, publish_outbox
from order_service.workers.task_dispatcher import run_task_dispatcher
from platform_auth import AuthClaims
from platform_observability import configure_application, metrics_response

settings = get_settings()
logger = logging.getLogger(settings.service_name)
allow_test_refund = settings.environment in {"local", "conformance"}


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.kafka_publisher_enabled:
        tasks.append(asyncio.create_task(publish_outbox(settings, stop)))
    if settings.kafka_consumer_enabled:
        tasks.append(asyncio.create_task(consume_saga_events(settings, stop)))
    if settings.invoice_consumer_enabled:
        tasks.append(asyncio.create_task(consume_invoice_events(settings, stop)))
    if settings.task_dispatcher_enabled:
        tasks.append(asyncio.create_task(run_task_dispatcher(settings, stop)))
    application.state.shipping_recovery_gateway = HttpShippingRecoveryGateway(settings)
    logger.info("service_started")
    yield
    stop.set()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await application.state.shipping_recovery_gateway.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Order Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/orders/admin/returns", response_model=ReturnRequestPage)
async def get_administrator_returns(
    return_status: ReturnStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    _: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> ReturnRequestPage:
    try:
        return await list_administrator_returns(
            db=db,
            status_filter=return_status,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from exc


@app.post(
    "/api/v1/orders/admin/returns/{return_request_id}/decision",
    response_model=ReturnRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_administrator_order_return(
    return_request_id: UUID,
    payload: ReturnDecisionRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> ReturnRequestResponse:
    return await decide_order_return(
        db,
        return_request_id=return_request_id,
        decided_by=claims.subject,
        idempotency_key=idempotency_key,
        payload=payload,
    )


@app.post(
    "/api/v1/orders/admin/returns/{return_request_id}/receipt",
    response_model=ReturnRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_administrator_order_return(
    return_request_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> ReturnRequestResponse:
    return await receive_order_return(
        db,
        return_request_id=return_request_id,
        received_by=claims.subject,
        idempotency_key=idempotency_key,
        allow_test_refund=allow_test_refund,
    )


@app.get("/api/v1/orders/admin", response_model=AdminOrderPage)
async def get_administrator_orders(
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    _: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> AdminOrderPage:
    try:
        return await list_administrator_orders(
            db=db,
            status_filter=order_status,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from exc


@app.get("/api/v1/orders/admin/{order_id}", response_model=AdminOrderResponse)
async def get_administrator_order(
    order_id: UUID,
    _: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> AdminOrderResponse:
    return await admin_order_response(db, await load_order_or_404(db, order_id))


@app.patch(
    "/api/v1/orders/admin/{order_id}/fulfillment",
    response_model=FulfillmentCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def update_administrator_order_fulfillment(
    order_id: UUID,
    payload: FulfillmentUpdateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_administrator),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> FulfillmentCommandResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    gateway: HttpShippingRecoveryGateway = app.state.shipping_recovery_gateway
    try:
        return await gateway.forward_fulfillment_command(
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            access_token=credentials.credentials,
        )
    except ShippingCommandUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="shipping command outcome is unavailable; retry with the same idempotency key",
        ) from exc


@app.post(
    "/api/v1/orders/admin/{order_id}/refund",
    response_model=RefundRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_administrator_order_refund(
    order_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> RefundRequestResponse:
    gateway: HttpShippingRecoveryGateway = app.state.shipping_recovery_gateway
    try:
        return await request_order_refund(
            db,
            order_id=order_id,
            requested_by=claims.subject,
            idempotency_key=idempotency_key,
            allow_test_refund=allow_test_refund,
            recover_expired_authorization=gateway.recover,
        )
    except ShippingRecoveryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="shipping recovery is unavailable; refund outcome is unchanged",
        ) from exc


@app.post(
    "/api/internal/v1/orders/{order_id}/fulfillment-authorizations",
    response_model=FulfillmentAuthorizationResponse,
    include_in_schema=False,
)
async def authorize_shipping_fulfillment_transition(
    order_id: UUID,
    payload: FulfillmentAuthorizationRequest,
    shipping_order_proof: str = Header(
        alias="X-Shipping-Order-Proof", min_length=64, max_length=64
    ),
    claims: AuthClaims = Depends(require_administrator),
    db: AsyncSession = Depends(get_session),
) -> FulfillmentAuthorizationResponse:
    verify_shipping_authorization_proof(
        settings=settings,
        provided_proof=shipping_order_proof,
        order_id=order_id,
        command_id=payload.command_id,
        target_status=payload.target_status,
        expires_at=payload.proof_expires_at,
    )
    authorization = await authorize_fulfillment_transition(
        db,
        order_id=order_id,
        command_id=payload.command_id,
        requested_by=claims.subject,
        target_status=payload.target_status,
        expires_at=payload.expires_at,
        max_ttl_seconds=settings.fulfillment_authorization_max_ttl_seconds,
    )
    return FulfillmentAuthorizationResponse(
        authorization_id=authorization.id,
        order_id=authorization.order_id,
        command_id=authorization.command_id,
        target_status=cast(FulfillmentStatus, authorization.target_status),
        expires_at=authorization.expires_at,
    )


@app.get("/api/v1/orders", response_model=CustomerOrderPage)
async def get_customer_orders(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> CustomerOrderPage:
    try:
        return await list_customer_orders(
            db=db,
            customer_id=claims.subject,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from exc


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    return await order_response(db, await load_owned_order_or_404(db, order_id, claims.subject))


@app.post(
    "/api/v1/orders/{order_id}/returns",
    response_model=ReturnRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_customer_order_return(
    order_id: UUID,
    payload: ReturnRequestCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_customer),
    db: AsyncSession = Depends(get_session),
) -> ReturnRequestResponse:
    return await request_order_return(
        db,
        order_id=order_id,
        requested_by=claims.subject,
        idempotency_key=idempotency_key,
        payload=payload,
    )


@app.post("/api/v1/orders", response_model=OrderResponse, status_code=status.HTTP_202_ACCEPTED)
async def checkout(
    payload: CheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_customer),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    quantities: dict[UUID, int] = {}
    for item in payload.items:
        if item.variant_id in quantities:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duplicate variant"
            )
        quantities[item.variant_id] = item.quantity
    address, customer_email, snapshots, currency, total = await collect_checkout_snapshot(
        catalog_base_url=settings.catalog_base_url,
        customer_base_url=settings.customer_base_url,
        access_token=credentials.credentials,
        address_id=payload.address_id,
        item_quantities=quantities,
    )
    validate_checkout_payment(
        payment_method=payload.payment_method, currency=currency, total_amount=total
    )
    return await order_response(
        db,
        await create_order(
            db,
            customer_id=claims.subject,
            idempotency_key=idempotency_key,
            delivery_address=address,
            customer_email=customer_email,
            snapshots=snapshots,
            currency=currency,
            total_amount=total,
            payment_method=payload.payment_method,
        ),
    )


@app.post(
    "/api/v1/orders/cart/zarinpal",
    response_model=CartCheckoutResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required or invalid"},
        status.HTTP_403_FORBIDDEN: {"description": "Customer role required"},
        status.HTTP_409_CONFLICT: {"description": "Cart, stock, or payment is unavailable"},
        status.HTTP_502_BAD_GATEWAY: {"description": "Payment provider rejected the request"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "A dependent service is unavailable or checkout is still preparing"
        },
    },
)
async def checkout_cart_with_zarinpal(
    payload: CartCheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_customer),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> CartCheckoutResponse:
    return await _checkout_cart_with_payment_method(
        payload=payload,
        idempotency_key=idempotency_key,
        claims=claims,
        credentials=credentials,
        db=db,
        payment_method="zarinpal",
    )


@app.post(
    "/api/v1/orders/cart/online",
    response_model=CartCheckoutResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required or invalid"},
        status.HTTP_403_FORBIDDEN: {"description": "Customer role required"},
        status.HTTP_409_CONFLICT: {"description": "Cart, stock, or payment is unavailable"},
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Every configured provider rejected the request"
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "A dependency is unavailable or checkout is still preparing"
        },
    },
)
async def checkout_cart_with_online_payment(
    payload: CartCheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    claims: AuthClaims = Depends(require_customer),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_session),
) -> CartCheckoutResponse:
    return await _checkout_cart_with_payment_method(
        payload=payload,
        idempotency_key=idempotency_key,
        claims=claims,
        credentials=credentials,
        db=db,
        payment_method="online",
    )


async def _checkout_cart_with_payment_method(
    *,
    payload: CartCheckoutRequest,
    idempotency_key: str,
    claims: AuthClaims,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    payment_method: str,
) -> CartCheckoutResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    cart_snapshot = None
    existing_order = await load_idempotent_order(
        db, customer_id=claims.subject, idempotency_key=idempotency_key
    )
    existing_order_id = existing_order.id if existing_order is not None else None
    await db.rollback()
    if existing_order is not None and existing_order.payment_method != payment_method:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key conflict")
    if existing_order is None:
        try:
            cart_snapshot = await fetch_cart_checkout_snapshot(
                base_url=settings.cart_base_url,
                timeout_seconds=settings.checkout_request_timeout_seconds,
                access_token=credentials.credentials,
            )
        except EmptyCart as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="cart is empty"
            ) from exc
        except CartGatewayUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="cart unavailable"
            ) from exc
        address, customer_email, snapshots, currency, total = await collect_checkout_snapshot(
            catalog_base_url=settings.catalog_base_url,
            customer_base_url=settings.customer_base_url,
            access_token=credentials.credentials,
            address_id=payload.address_id,
            item_quantities=cart_snapshot.item_quantities,
        )
        validate_checkout_payment(
            payment_method=payment_method, currency=currency, total_amount=total
        )
        created_order = await create_order(
            db,
            customer_id=claims.subject,
            idempotency_key=idempotency_key,
            delivery_address=address,
            customer_email=customer_email,
            snapshots=snapshots,
            currency=currency,
            total_amount=total,
            payment_method=payment_method,
        )
        order_id = created_order.id
    else:
        if existing_order_id is None:
            raise RuntimeError("idempotent order id was not loaded")
        order_id = existing_order_id

    ready_order = await wait_for_payment_pending(
        session_factory=get_session_factory(),
        order_id=order_id,
        timeout_seconds=settings.checkout_redirect_wait_seconds,
        poll_interval_seconds=settings.checkout_redirect_poll_interval_seconds,
    )
    if ready_order is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="checkout is still preparing payment; retry with the same idempotency key",
        )
    if ready_order.status == "CANCELLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="checkout was cancelled")

    try:
        if payment_method == "online":
            payment = await start_online_checkout(
                base_url=settings.payment_base_url,
                timeout_seconds=settings.checkout_request_timeout_seconds,
                order_id=order_id,
                access_token=credentials.credentials,
            )
        else:
            payment = await start_zarinpal_checkout(
                base_url=settings.payment_base_url,
                timeout_seconds=settings.checkout_request_timeout_seconds,
                order_id=order_id,
                access_token=credentials.credentials,
            )
    except PaymentNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="payment not ready"
        ) from exc
    except PaymentProviderRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="payment provider rejected request"
        ) from exc
    except PaymentProviderNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payment provider is not configured",
        ) from exc
    except PaymentGatewayUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="payment provider unavailable"
        ) from exc

    if cart_snapshot is not None:
        try:
            cart_cleared = await consume_cart_checkout_snapshot(
                base_url=settings.cart_base_url,
                timeout_seconds=settings.checkout_request_timeout_seconds,
                access_token=credentials.credentials,
                snapshot=cart_snapshot,
            )
            if not cart_cleared:
                logger.info(
                    "cart_changed_before_checkout_cleanup", extra={"order_id": str(order_id)}
                )
        except CartGatewayUnavailable:
            logger.warning("cart_checkout_cleanup_unavailable", extra={"order_id": str(order_id)})

    return CartCheckoutResponse(
        order=ready_order,
        redirect_url=payment.redirect_url,
        expires_at=payment.expires_at,
    )


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()
