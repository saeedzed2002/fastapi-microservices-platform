import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Query, WebSocket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chat_service.application import (
    create_conversation,
    get_attachment_download_url,
    get_conversation,
    list_conversations,
    list_messages,
    mark_read,
)
from chat_service.auth import current_user
from chat_service.config import get_settings
from chat_service.db import dispose_engine, get_session, get_session_factory
from chat_service.media import HttpMediaAttachmentGateway
from chat_service.realtime import ChatRealtime, ChatWebSocketHandler, ConnectionHub
from chat_service.schemas import (
    AttachmentDownloadResponse,
    ConversationCreate,
    ConversationPage,
    ConversationResponse,
    MarkReadRequest,
    MarkReadResponse,
    MessagePage,
    PresenceResponse,
)
from platform_auth import AuthClaims

settings = get_settings()
logger = logging.getLogger(settings.service_name)
hub = ConnectionHub()
realtime = ChatRealtime(settings, hub)
media_gateway = HttpMediaAttachmentGateway(settings)
websocket_handler = ChatWebSocketHandler(
    settings=settings,
    realtime=realtime,
    media_gateway=media_gateway,
    session_factory=get_session_factory(),
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await realtime.start()
    logger.info("service_started")
    yield
    await realtime.stop()
    await media_gateway.close()
    await dispose_engine()
    logger.info("service_stopped")


app = FastAPI(title="Chat Service", version=settings.service_version, lifespan=lifespan)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/v1/chat/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation_endpoint(
    payload: ConversationCreate,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    return await create_conversation(db, subject_id=claims.subject, payload=payload)


@app.get("/api/v1/chat/conversations", response_model=ConversationPage)
async def list_conversations_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationPage:
    return await list_conversations(db, subject_id=claims.subject, limit=limit)


@app.get("/api/v1/chat/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_endpoint(
    conversation_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    return await get_conversation(db, conversation_id=conversation_id, subject_id=claims.subject)


@app.get("/api/v1/chat/conversations/{conversation_id}/messages", response_model=MessagePage)
async def list_messages_endpoint(
    conversation_id: UUID,
    before: str | None = None,
    after: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> MessagePage:
    return await list_messages(
        db,
        conversation_id=conversation_id,
        subject_id=claims.subject,
        limit=limit,
        before=before,
        after=after,
    )


@app.post("/api/v1/chat/conversations/{conversation_id}/read", response_model=MarkReadResponse)
async def mark_read_endpoint(
    conversation_id: UUID,
    payload: MarkReadRequest,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> MarkReadResponse:
    return await mark_read(
        db,
        conversation_id=conversation_id,
        subject_id=claims.subject,
        message_id=payload.message_id,
    )


@app.get("/api/v1/chat/presence/{subject_id}", response_model=PresenceResponse)
async def get_presence_endpoint(
    subject_id: UUID,
    _: AuthClaims = Depends(current_user),
) -> PresenceResponse:
    return PresenceResponse(
        subject_id=subject_id, status=await realtime.presence_status(subject_id=subject_id)
    )


@app.get(
    "/api/v1/chat/conversations/{conversation_id}/messages/{message_id}/attachments/{asset_id}/download-url",
    response_model=AttachmentDownloadResponse,
)
async def get_attachment_download_url_endpoint(
    conversation_id: UUID,
    message_id: UUID,
    asset_id: UUID,
    claims: AuthClaims = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> AttachmentDownloadResponse:
    return await get_attachment_download_url(
        db,
        conversation_id=conversation_id,
        message_id=message_id,
        asset_id=asset_id,
        subject_id=claims.subject,
        media_gateway=media_gateway,
    )


@app.websocket("/api/v1/chat/ws")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket_handler.serve(websocket)


@app.get("/metrics", tags=["observability"])
async def metrics() -> str:
    return realtime.render_metrics()
