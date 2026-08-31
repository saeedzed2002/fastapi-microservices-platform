import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.application import (
    OtpDeliveryUnavailable,
    OtpNotEligible,
    request_customer_otp,
    verify_customer_otp,
)
from identity_service.config import get_settings
from identity_service.db import dispose_engine, get_session
from identity_service.models import (
    AuthenticationAuditEvent,
    PasswordResetRequest,
    RefreshSession,
    User,
)
from identity_service.notification import (
    NotificationOtpGateway,
    NotificationPasswordResetGateway,
    NotificationUnavailable,
)
from identity_service.otp import OtpBusy, OtpInvalid, OtpRateLimited, OtpStateStore, OtpUnavailable
from identity_service.password_reset import (
    PasswordResetDeliveryUnavailable,
    PasswordResetRateLimited,
    PasswordResetStateStore,
    PasswordResetUnavailable,
)
from identity_service.schemas import (
    InternalOtpDeliveryCodeResponse,
    InternalPasswordResetDeliveryResponse,
    LoginRequest,
    LogoutRequest,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    RefreshRequest,
    SessionPage,
    SessionResponse,
    TokenResponse,
    UserResponse,
)
from identity_service.security import (
    create_refresh_token,
    hash_password,
    parse_refresh_session_id,
    refresh_expiry,
    token_hash,
    verify_password,
)
from identity_service.staff_login_rate_limit import (
    StaffLoginRateLimited,
    StaffLoginRateLimiter,
    StaffLoginRateLimitUnavailable,
)
from identity_service.workers.outbox_publisher import run_outbox_publisher
from platform_auth import AuthClaims, TokenError, decode_access_token, encode_access_token
from platform_observability import configure_application, metrics_response

settings = get_settings()
logger = logging.getLogger(settings.service_name)
bearer = HTTPBearer(auto_error=False)
otp_state_store = OtpStateStore(settings)
otp_notification_gateway = NotificationOtpGateway(settings)
password_reset_state_store = PasswordResetStateStore(settings)
password_reset_notification_gateway = NotificationPasswordResetGateway(settings)
staff_login_rate_limiter = StaffLoginRateLimiter(settings)
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$Qzj/JYfZ/ZC5F/LkrNMdZw$"
    "ucEKiYXYn4tR0EYAW272goP7D0salWXWX4lr71cI1Mc"
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    publisher_task: asyncio.Task[None] | None = None
    if settings.kafka_publisher_enabled:
        publisher_task = asyncio.create_task(run_outbox_publisher(settings, stop))
    logger.info("service_started")
    yield
    stop.set()
    if publisher_task is not None:
        publisher_task.cancel()
        await asyncio.gather(publisher_task, return_exceptions=True)
    await otp_notification_gateway.close()
    await password_reset_notification_gateway.close()
    await otp_state_store.close()
    await password_reset_state_store.close()
    await staff_login_rate_limiter.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Identity Service", version=settings.service_version, lifespan=lifespan)
configure_application(
    app,
    service_name=settings.service_name,
    service_version=settings.service_version,
    environment=settings.environment,
    log_level=settings.log_level,
)


def require_internal_identity_token(token: str | None) -> None:
    expected = settings.internal_otp_shared_secret
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal service authentication is not configured",
        )
    if token is None or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="internal authentication required"
        )


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        status=user.status,
        roles=list(user.roles),
        created_at=user.created_at,
    )


def issue_access_token(user: User) -> str:
    return encode_access_token(
        subject=user.id,
        roles=tuple(user.roles),
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_seconds=settings.access_token_ttl_seconds,
    )


async def create_session(
    db: AsyncSession,
    *,
    user: User,
    request: Request,
    family_id: UUID | None = None,
) -> str:
    session_id = uuid4()
    refresh_token = create_refresh_token(session_id)
    db.add(
        RefreshSession(
            id=session_id,
            user_id=user.id,
            family_id=family_id or uuid4(),
            token_hash=token_hash(refresh_token),
            expires_at=refresh_expiry(settings),
            user_agent=_request_user_agent(request),
            ip_hash=_request_ip_hash(request),
        )
    )
    return refresh_token


def _request_user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:512] if value else None


def _request_ip_hash(request: Request) -> str | None:
    client_host = request.client.host if request.client is not None else None
    if client_host is None:
        return None
    return hmac.new(
        settings.session_metadata_hmac_secret.encode("utf-8"),
        client_host.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def session_response(session: RefreshSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        user_agent=session.user_agent,
        created_at=session.created_at,
        last_used_at=session.last_used_at,
        expires_at=session.expires_at,
    )


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthClaims:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        return decode_access_token(
            credentials.credentials,
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token"
        ) from exc


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get(
    "/internal/v1/otp-deliveries/{delivery_id}/code",
    response_model=InternalOtpDeliveryCodeResponse,
    include_in_schema=False,
)
async def get_otp_delivery_code(
    delivery_id: UUID,
    internal_token: str | None = Header(default=None, alias="X-Platform-Internal-Token"),
) -> InternalOtpDeliveryCodeResponse:
    require_internal_identity_token(internal_token)
    try:
        challenge = await otp_state_store.get_delivery_challenge(delivery_id)
    except OtpInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OTP delivery is unavailable"
        ) from exc
    except OtpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OTP delivery is unavailable",
        ) from exc
    return InternalOtpDeliveryCodeResponse(phone=challenge.phone, otp_code=challenge.code)


@app.post("/api/v1/auth/register", status_code=status.HTTP_410_GONE, deprecated=True)
async def register() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="customer password registration is disabled; use /api/v1/auth/otp/request",
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        await staff_login_rate_limiter.check_allowed(email=payload.email)
    except StaffLoginRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="staff login rate limit exceeded",
            headers={"Retry-After": str(settings.staff_login_lockout_seconds)},
        ) from exc
    except StaffLoginRateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="staff login is temporarily unavailable",
        ) from exc

    user = await db.scalar(select(User).where(User.email == payload.email))
    password_valid = verify_password(
        payload.password,
        user.password_hash
        if user is not None and user.password_hash is not None
        else _DUMMY_PASSWORD_HASH,
    )
    staff_eligible = not (
        user is None
        or user.status != "active"
        or "admin" not in user.roles
        or user.password_hash is None
    )
    if not staff_eligible or not password_valid:
        await db.rollback()
        try:
            retry_after = await staff_login_rate_limiter.record_failure(email=payload.email)
        except StaffLoginRateLimitUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="staff login is temporarily unavailable",
            ) from exc
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="staff login rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    if user is None:
        raise AssertionError("eligible staff login requires a user")
    user_id = user.id
    await db.rollback()
    try:
        await staff_login_rate_limiter.record_success(email=payload.email)
    except StaffLoginRateLimitUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="staff login is temporarily unavailable",
        ) from exc
    user = await db.get(User, user_id)
    if (
        user is None
        or user.status != "active"
        or "admin" not in user.roles
        or user.password_hash is None
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    refresh_token = await create_session(db, user=user, request=request)
    await db.commit()
    return TokenResponse(
        access_token=issue_access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@app.post(
    "/api/v1/auth/otp/request",
    response_model=OtpRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_otp(payload: OtpRequest) -> OtpRequestResponse:
    try:
        await request_customer_otp(
            phone=payload.phone,
            state_store=otp_state_store,
            notification_gateway=otp_notification_gateway,
        )
    except OtpRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="OTP request rate limit exceeded",
        ) from exc
    except (OtpUnavailable, OtpDeliveryUnavailable) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OTP delivery is unavailable",
        ) from exc
    return OtpRequestResponse(expires_in=settings.otp_code_ttl_seconds)


@app.post("/api/v1/auth/otp/verify", response_model=TokenResponse)
async def verify_otp(
    payload: OtpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        user = await verify_customer_otp(
            db=db,
            phone=payload.phone,
            code=payload.code,
            state_store=otp_state_store,
            settings=settings,
        )
    except OtpBusy as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OTP verification is already in progress",
        ) from exc
    except OtpInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP is invalid or expired",
        ) from exc
    except OtpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OTP verification is unavailable",
        ) from exc
    except OtpNotEligible as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OTP account is not eligible for customer authentication",
        ) from exc
    refresh_token = await create_session(db, user=user, request=request)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="phone already registered"
        ) from exc
    await db.refresh(user)
    return TokenResponse(
        access_token=issue_access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@app.post(
    "/api/v1/auth/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    payload: PasswordResetRequestPayload,
    db: AsyncSession = Depends(get_session),
) -> PasswordResetRequestResponse:
    """Start a non-enumerating reset flow for password-bearing staff accounts only."""

    user = await db.scalar(select(User).where(User.email == payload.email))
    eligible = (
        user is not None
        and user.status == "active"
        and "admin" in user.roles
        and user.password_hash is not None
    )
    await db.rollback()
    if not eligible or user is None:
        return PasswordResetRequestResponse()

    delivery_id = uuid4()
    try:
        delivery = await password_reset_state_store.create_delivery(
            delivery_id=delivery_id,
            email=payload.email,
        )
    except PasswordResetRateLimited:
        return PasswordResetRequestResponse()
    except PasswordResetUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="password reset is temporarily unavailable",
        ) from exc

    try:
        locked_user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
        if (
            locked_user is None
            or locked_user.status != "active"
            or "admin" not in locked_user.roles
            or locked_user.password_hash is None
        ):
            await db.rollback()
            await password_reset_state_store.discard_delivery(delivery)
            return PasswordResetRequestResponse()
        now = datetime.now(UTC)
        await db.execute(
            update(PasswordResetRequest)
            .where(
                PasswordResetRequest.user_id == locked_user.id,
                PasswordResetRequest.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        db.add(
            PasswordResetRequest(
                id=delivery_id,
                user_id=locked_user.id,
                token_hash=token_hash(delivery.token),
                expires_at=now + timedelta(seconds=settings.password_reset_token_ttl_seconds),
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await password_reset_state_store.discard_delivery(delivery)
        raise

    try:
        await password_reset_notification_gateway.enqueue(
            delivery_id=delivery.delivery_id,
            email=delivery.email,
        )
    except NotificationUnavailable as exc:
        failed_request = await db.scalar(
            select(PasswordResetRequest)
            .where(PasswordResetRequest.id == delivery.delivery_id)
            .with_for_update()
        )
        if failed_request is not None and failed_request.consumed_at is None:
            failed_request.consumed_at = datetime.now(UTC)
            await db.commit()
        await password_reset_state_store.discard_delivery(delivery)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="password reset delivery is temporarily unavailable",
        ) from exc
    return PasswordResetRequestResponse()


@app.post("/api/v1/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    payload: PasswordResetConfirmPayload,
    db: AsyncSession = Depends(get_session),
) -> None:
    try:
        reset_request_id = PasswordResetStateStore.parse_token(payload.token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password reset token is invalid or expired",
        ) from exc

    reset_request = await db.scalar(
        select(PasswordResetRequest)
        .where(PasswordResetRequest.id == reset_request_id)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        reset_request is None
        or reset_request.consumed_at is not None
        or reset_request.expires_at.replace(tzinfo=UTC) <= now
        or reset_request.token_hash != token_hash(payload.token)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password reset token is invalid or expired",
        )
    user = await db.get(User, reset_request.user_id)
    if (
        user is None
        or user.status != "active"
        or "admin" not in user.roles
        or user.password_hash is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password reset token is invalid or expired",
        )

    user.password_hash = hash_password(payload.new_password)
    reset_request.consumed_at = now
    await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.add(
        AuthenticationAuditEvent(
            actor_user_id=user.id,
            target_user_id=user.id,
            event_type="staff.password_reset_completed.v1",
            details={"reset_request_id": str(reset_request.id)},
        )
    )
    await db.commit()
    await password_reset_state_store.discard_delivery_id(reset_request.id)


@app.get(
    "/internal/v1/password-reset-deliveries/{delivery_id}",
    response_model=InternalPasswordResetDeliveryResponse,
    include_in_schema=False,
)
async def get_password_reset_delivery(
    delivery_id: UUID,
    internal_token: str | None = Header(default=None, alias="X-Platform-Internal-Token"),
    db: AsyncSession = Depends(get_session),
) -> InternalPasswordResetDeliveryResponse:
    require_internal_identity_token(internal_token)
    try:
        delivery = await password_reset_state_store.get_delivery(delivery_id)
    except PasswordResetDeliveryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="password reset delivery is unavailable",
        ) from exc
    except PasswordResetUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="password reset delivery is unavailable",
        ) from exc
    reset_request = await db.get(PasswordResetRequest, delivery_id)
    now = datetime.now(UTC)
    if (
        reset_request is None
        or reset_request.consumed_at is not None
        or reset_request.expires_at.replace(tzinfo=UTC) <= now
        or reset_request.token_hash != token_hash(delivery.token)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="password reset delivery is unavailable",
        )
    user = await db.get(User, reset_request.user_id)
    if user is None or user.email != delivery.email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="password reset delivery is unavailable",
        )
    return InternalPasswordResetDeliveryResponse(email=delivery.email, token=delivery.token)


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        session_id = parse_refresh_session_id(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        ) from exc

    session = await db.scalar(
        select(RefreshSession).where(RefreshSession.id == session_id).with_for_update()
    )
    now = datetime.now(UTC)
    supplied_token_hash = token_hash(payload.refresh_token)
    valid_session = (
        session is not None
        and session.revoked_at is None
        and session.expires_at.replace(tzinfo=UTC) > now
        and session.token_hash == supplied_token_hash
    )
    if not valid_session:
        if (
            session is not None
            and session.revoked_at is not None
            and session.token_hash == supplied_token_hash
        ):
            await db.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.family_id == session.family_id,
                    RefreshSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        )
    assert session is not None

    user = await db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        )

    session.revoked_at = now
    replacement = await create_session(
        db,
        user=user,
        request=request,
        family_id=session.family_id,
    )
    session.replaced_by_session_id = parse_refresh_session_id(replacement)
    await db.commit()
    return TokenResponse(
        access_token=issue_access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=replacement,
        user=user_response(user),
    )


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_session)) -> None:
    try:
        session_id = parse_refresh_session_id(payload.refresh_token)
    except ValueError:
        return
    session = await db.get(RefreshSession, session_id)
    if session is not None and session.token_hash == token_hash(payload.refresh_token):
        session.revoked_at = datetime.now(UTC)
        await db.commit()


@app.get("/api/v1/auth/sessions", response_model=SessionPage)
async def list_sessions(
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> SessionPage:
    sessions = list(
        (
            await db.scalars(
                select(RefreshSession)
                .where(
                    RefreshSession.user_id == claims.subject,
                    RefreshSession.revoked_at.is_(None),
                )
                .order_by(RefreshSession.last_used_at.desc(), RefreshSession.created_at.desc())
            )
        ).all()
    )
    return SessionPage(items=[session_response(session) for session in sessions])


@app.delete("/api/v1/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    session = await db.scalar(
        select(RefreshSession).where(RefreshSession.id == session_id).with_for_update()
    )
    if session is None or session.user_id != claims.subject or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    session.revoked_at = datetime.now(UTC)
    await db.commit()


@app.post("/api/v1/auth/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == claims.subject,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def me(
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    user = await db.get(User, claims.subject)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user is inactive")
    return user_response(user)


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return metrics_response()


@app.get("/api/v1/auth/context", include_in_schema=False)
async def auth_context(
    request: Request, claims: AuthClaims = Depends(current_user)
) -> dict[str, Any]:
    return {"user_id": str(claims.subject), "request_id": request.headers.get("x-request-id")}
