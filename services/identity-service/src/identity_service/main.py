import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.config import get_settings
from identity_service.db import dispose_engine, get_session
from identity_service.models import OutboxMessage, RefreshSession, User
from identity_service.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
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
from identity_service.workers.outbox_publisher import run_outbox_publisher
from platform_auth import AuthClaims, TokenError, decode_access_token, encode_access_token

settings = get_settings()
logger = logging.getLogger(settings.service_name)
bearer = HTTPBearer(auto_error=False)


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
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Identity Service", version=settings.service_version, lifespan=lifespan)


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
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
        )
    )
    return refresh_token


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


@app.post(
    "/api/v1/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_session)
) -> TokenResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    await db.flush()
    db.add(
        OutboxMessage(
            event_type="identity.user_registered.v1",
            aggregate_type="user",
            aggregate_id=user.id,
            payload={"user_id": str(user.id), "email": user.email, "roles": list(user.roles)},
            headers={"producer": settings.service_name},
        )
    )
    refresh_token = await create_session(db, user=user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        ) from exc
    await db.refresh(user)
    return TokenResponse(
        access_token=issue_access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_session)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if (
        user is None
        or user.status != "active"
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    refresh_token = await create_session(db, user=user)
    await db.commit()
    return TokenResponse(
        access_token=issue_access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, db: AsyncSession = Depends(get_session)
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
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at.replace(tzinfo=UTC) <= now
        or session.token_hash != token_hash(payload.refresh_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        )

    user = await db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        )

    session.revoked_at = now
    replacement = await create_session(db, user=user, family_id=session.family_id)
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
async def metrics() -> str:
    return (
        "# HELP identity_service_up Service availability\n"
        "# TYPE identity_service_up gauge\n"
        "identity_service_up 1\n"
    )


@app.get("/api/v1/auth/context", include_in_schema=False)
async def auth_context(
    request: Request, claims: AuthClaims = Depends(current_user)
) -> dict[str, Any]:
    return {"user_id": str(claims.subject), "request_id": request.headers.get("x-request-id")}
