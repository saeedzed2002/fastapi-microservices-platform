import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.application import SentMessage, send_message
from chat_service.auth import decode_chat_access_token
from chat_service.config import Settings
from chat_service.media import MediaAttachmentGateway
from chat_service.schemas import (
    AuthenticateFrame,
    HeartbeatFrame,
    MessageResponse,
    SendMessageFrame,
)

logger = logging.getLogger(__name__)


class FanoutNotification(BaseModel):
    origin_instance_id: str = Field(min_length=1, max_length=128)
    participant_ids: list[UUID] = Field(min_length=1, max_length=25)
    message: MessageResponse


@dataclass
class LocalConnection:
    websocket: WebSocket
    subject_id: UUID
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[UUID, LocalConnection] = {}
        self._by_subject: dict[UUID, set[UUID]] = defaultdict(set)

    def add(self, *, websocket: WebSocket, subject_id: UUID) -> UUID:
        connection_id = uuid4()
        self._connections[connection_id] = LocalConnection(
            websocket=websocket, subject_id=subject_id
        )
        self._by_subject[subject_id].add(connection_id)
        return connection_id

    def remove(self, connection_id: UUID) -> None:
        connection = self._connections.pop(connection_id, None)
        if connection is None:
            return
        connection_ids = self._by_subject.get(connection.subject_id)
        if connection_ids is None:
            return
        connection_ids.discard(connection_id)
        if not connection_ids:
            self._by_subject.pop(connection.subject_id, None)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, *, participant_ids: list[UUID], message: MessageResponse) -> None:
        payload = {
            "type": "chat.message.v1",
            "conversation_id": str(message.conversation_id),
            "message_id": str(message.id),
            "client_message_id": str(message.client_message_id),
            "sender_id": str(message.sender_id),
            "content": message.content,
            "attachments": [
                attachment.model_dump(mode="json") for attachment in message.attachments
            ],
            "created_at": message.created_at.isoformat(),
        }
        stale_connections: list[UUID] = []
        connection_ids = {
            connection_id
            for subject_id in participant_ids
            for connection_id in self._by_subject.get(subject_id, set())
        }
        for connection_id in connection_ids:
            connection = self._connections.get(connection_id)
            if connection is None:
                continue
            try:
                async with connection.send_lock:
                    await connection.websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(connection_id)
        for connection_id in stale_connections:
            self.remove(connection_id)


class ChatRealtime:
    def __init__(self, settings: Settings, hub: ConnectionHub) -> None:
        self._settings = settings
        self._hub = hub
        self._client: Redis | None = (
            Redis.from_url(settings.redis_url, decode_responses=True, health_check_interval=30)
            if settings.redis_enabled
            else None
        )
        self._stop = asyncio.Event()
        self._subscriber_task: asyncio.Task[None] | None = None
        self._pubsub: Any | None = None
        self._message_acknowledgements = 0
        self._redis_fanout_publish_failures = 0
        self._redis_fanout_subscriber_failures = 0
        self._presence_failures = 0
        self._connection_rate_limit_rejections = 0
        self._websocket_request_errors = 0

    async def start(self) -> None:
        if self._client is not None and self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(self._run_subscriber())

    async def stop(self) -> None:
        self._stop.set()
        if self._pubsub is not None:
            await self._pubsub.aclose()
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            await asyncio.gather(self._subscriber_task, return_exceptions=True)
            self._subscriber_task = None
        if self._client is not None:
            await self._client.aclose()

    async def allow_connection(self, *, remote_ip: str) -> bool:
        if self._client is None:
            self._connection_rate_limit_rejections += 1
            return False
        key = f"fastapi-platform:chat:ws-rate:v1:{remote_ip}"
        try:
            count = await self._client.incr(key)
            if count == 1:
                await self._client.expire(
                    key, self._settings.websocket_connection_rate_window_seconds
                )
            allowed = count <= self._settings.websocket_connection_rate_limit
            if not allowed:
                self._connection_rate_limit_rejections += 1
            return allowed
        except RedisError:
            self._connection_rate_limit_rejections += 1
            logger.warning("websocket_connection_rate_limit_unavailable")
            return False

    def register_connection(self, *, websocket: WebSocket, subject_id: UUID) -> UUID:
        return self._hub.add(websocket=websocket, subject_id=subject_id)

    def remove_connection(self, connection_id: UUID) -> None:
        self._hub.remove(connection_id)

    async def enter_presence(self, *, subject_id: UUID, connection_id: UUID) -> None:
        await self._refresh_presence(subject_id=subject_id, connection_id=connection_id)

    async def refresh_presence(self, *, subject_id: UUID, connection_id: UUID) -> None:
        await self._refresh_presence(subject_id=subject_id, connection_id=connection_id)

    async def _refresh_presence(self, *, subject_id: UUID, connection_id: UUID) -> None:
        if self._client is None:
            return
        key = self._presence_key(subject_id)
        try:
            await self._client.zadd(
                key,
                {
                    f"{self._settings.redis_instance_id}:{connection_id}": time.time()
                    + self._settings.presence_ttl_seconds
                },
            )
            await self._client.expire(key, self._settings.presence_ttl_seconds * 2)
        except RedisError:
            self._presence_failures += 1
            logger.warning("chat_presence_unavailable")

    async def leave_presence(self, *, subject_id: UUID, connection_id: UUID) -> None:
        if self._client is None:
            return
        try:
            await self._client.zrem(
                self._presence_key(subject_id),
                f"{self._settings.redis_instance_id}:{connection_id}",
            )
        except RedisError:
            self._presence_failures += 1
            logger.warning("chat_presence_unavailable")

    async def presence_status(self, *, subject_id: UUID) -> Literal["online", "offline", "unknown"]:
        if self._client is None:
            return "unknown"
        key = self._presence_key(subject_id)
        try:
            await self._client.zremrangebyscore(key, 0, time.time())
            return "online" if await self._client.zcard(key) > 0 else "offline"
        except RedisError:
            self._presence_failures += 1
            logger.warning("chat_presence_unavailable")
            return "unknown"

    async def fanout(self, sent_message: SentMessage) -> None:
        await self._hub.broadcast(
            participant_ids=sent_message.participant_ids,
            message=sent_message.message,
        )
        if self._client is None or sent_message.duplicate:
            return
        notification = FanoutNotification(
            origin_instance_id=self._settings.redis_instance_id,
            participant_ids=sent_message.participant_ids,
            message=sent_message.message,
        )
        try:
            await self._client.publish(self._settings.redis_channel, notification.model_dump_json())
        except RedisError:
            self._redis_fanout_publish_failures += 1
            logger.warning("chat_fanout_publish_failed")

    def record_message_acknowledgement(self) -> None:
        self._message_acknowledgements += 1

    def record_websocket_request_error(self) -> None:
        self._websocket_request_errors += 1

    def render_metrics(self) -> str:
        return "\n".join(
            (
                "# HELP chat_service_up Service availability",
                "# TYPE chat_service_up gauge",
                "chat_service_up 1",
                "# HELP chat_websocket_connections Active authenticated WebSocket connections",
                "# TYPE chat_websocket_connections gauge",
                f"chat_websocket_connections {self._hub.connection_count}",
                "# HELP chat_message_acknowledgements_total Durable message acknowledgements",
                "# TYPE chat_message_acknowledgements_total counter",
                f"chat_message_acknowledgements_total {self._message_acknowledgements}",
                "# HELP chat_redis_fanout_publish_failures_total "
                "Redis fan-out publication failures",
                "# TYPE chat_redis_fanout_publish_failures_total counter",
                f"chat_redis_fanout_publish_failures_total {self._redis_fanout_publish_failures}",
                "# HELP chat_redis_fanout_subscriber_failures_total Redis subscriber failures",
                "# TYPE chat_redis_fanout_subscriber_failures_total counter",
                "chat_redis_fanout_subscriber_failures_total "
                f"{self._redis_fanout_subscriber_failures}",
                "# HELP chat_presence_failures_total Redis presence failures",
                "# TYPE chat_presence_failures_total counter",
                f"chat_presence_failures_total {self._presence_failures}",
                "# HELP chat_websocket_connection_rate_limit_rejections_total Rejected connections",
                "# TYPE chat_websocket_connection_rate_limit_rejections_total counter",
                "chat_websocket_connection_rate_limit_rejections_total "
                f"{self._connection_rate_limit_rejections}",
                "# HELP chat_websocket_request_errors_total Rejected WebSocket request frames",
                "# TYPE chat_websocket_request_errors_total counter",
                f"chat_websocket_request_errors_total {self._websocket_request_errors}",
                "",
            )
        )

    def _presence_key(self, subject_id: UUID) -> str:
        return f"fastapi-platform:chat:presence:v1:{subject_id}"

    async def _run_subscriber(self) -> None:
        delay = self._settings.redis_subscriber_retry_seconds
        while not self._stop.is_set():
            try:
                await self._listen_once()
                delay = self._settings.redis_subscriber_retry_seconds
            except asyncio.CancelledError:
                raise
            except RedisError:
                self._redis_fanout_subscriber_failures += 1
                logger.warning("chat_fanout_subscriber_unavailable")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except TimeoutError:
                    delay = min(delay * 2, self._settings.redis_subscriber_max_retry_seconds)

    async def _listen_once(self) -> None:
        if self._client is None:
            return
        pubsub = self._client.pubsub()
        self._pubsub = pubsub
        try:
            await pubsub.subscribe(self._settings.redis_channel)
            while not self._stop.is_set():
                received = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if received is None or not isinstance(received.get("data"), str):
                    continue
                try:
                    notification = FanoutNotification.model_validate_json(received["data"])
                except ValidationError:
                    logger.warning("chat_fanout_notification_invalid")
                    continue
                if notification.origin_instance_id == self._settings.redis_instance_id:
                    continue
                await self._hub.broadcast(
                    participant_ids=notification.participant_ids,
                    message=notification.message,
                )
        finally:
            self._pubsub = None
            await pubsub.aclose()  # type: ignore[no-untyped-call]


class ChatWebSocketHandler:
    def __init__(
        self,
        *,
        settings: Settings,
        realtime: ChatRealtime,
        media_gateway: MediaAttachmentGateway,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._realtime = realtime
        self._media_gateway = media_gateway
        self._session_factory = session_factory

    async def serve(self, websocket: WebSocket) -> None:
        await websocket.accept()
        remote_ip = websocket.client.host if websocket.client is not None else "unknown"
        if not await self._realtime.allow_connection(remote_ip=remote_ip):
            await self._send_error(
                websocket, code="connection_unavailable", message="connection unavailable"
            )
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return
        try:
            auth_payload = await asyncio.wait_for(
                self._receive_payload(websocket),
                timeout=self._settings.websocket_auth_timeout_seconds,
            )
            auth_frame = AuthenticateFrame.model_validate(auth_payload)
            claims = decode_chat_access_token(auth_frame.access_token, self._settings)
        except (TimeoutError, ValidationError, ValueError):
            await self._send_error(
                websocket, code="authentication_required", message="valid authentication required"
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        connection_id = self._realtime.register_connection(
            websocket=websocket, subject_id=claims.subject
        )
        refresh_task = asyncio.create_task(
            self._refresh_presence(subject_id=claims.subject, connection_id=connection_id)
        )
        try:
            await self._realtime.enter_presence(
                subject_id=claims.subject, connection_id=connection_id
            )
            await websocket.send_json(
                {
                    "type": "chat.authenticated.v1",
                    "request_id": str(auth_frame.request_id),
                    "subject_id": str(claims.subject),
                }
            )
            while True:
                try:
                    payload = await self._receive_payload(websocket)
                    await self._handle_payload(
                        websocket=websocket,
                        subject_id=claims.subject,
                        access_token=auth_frame.access_token,
                        payload=payload,
                    )
                except HTTPException as exc:
                    self._realtime.record_websocket_request_error()
                    await self._send_error(
                        websocket,
                        code="request_rejected",
                        message=str(exc.detail),
                    )
                except (ValidationError, ValueError):
                    self._realtime.record_websocket_request_error()
                    await self._send_error(
                        websocket, code="invalid_frame", message="invalid client frame"
                    )
        except WebSocketDisconnect:
            return
        finally:
            refresh_task.cancel()
            await asyncio.gather(refresh_task, return_exceptions=True)
            await self._realtime.leave_presence(
                subject_id=claims.subject, connection_id=connection_id
            )
            self._realtime.remove_connection(connection_id)

    async def _handle_payload(
        self,
        *,
        websocket: WebSocket,
        subject_id: UUID,
        access_token: str,
        payload: dict[str, Any],
    ) -> None:
        frame_type = payload.get("type")
        if frame_type == "chat.heartbeat.v1":
            heartbeat_frame = HeartbeatFrame.model_validate(payload)
            await websocket.send_json(
                {"type": "chat.heartbeat_ack.v1", "request_id": str(heartbeat_frame.request_id)}
            )
            return
        if frame_type != "chat.send_message.v1":
            raise ValueError("unsupported client frame")
        send_frame = SendMessageFrame.model_validate(payload)
        async with self._session_factory() as db:
            sent_message = await send_message(
                db,
                sender_subject_id=subject_id,
                access_token=access_token,
                payload=send_frame,
                media_gateway=self._media_gateway,
            )
        await websocket.send_json(
            {
                "type": "chat.message_ack.v1",
                "request_id": str(send_frame.request_id),
                "conversation_id": str(sent_message.message.conversation_id),
                "message_id": str(sent_message.message.id),
                "created_at": sent_message.message.created_at.isoformat(),
                "duplicate": sent_message.duplicate,
            }
        )
        self._realtime.record_message_acknowledgement()
        await self._realtime.fanout(sent_message)

    async def _refresh_presence(self, *, subject_id: UUID, connection_id: UUID) -> None:
        while True:
            await asyncio.sleep(self._settings.presence_refresh_seconds)
            await self._realtime.refresh_presence(
                subject_id=subject_id, connection_id=connection_id
            )

    async def _receive_payload(self, websocket: WebSocket) -> dict[str, Any]:
        text = await websocket.receive_text()
        if len(text.encode()) > self._settings.websocket_max_frame_bytes:
            raise ValueError("frame too large")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("frame must be an object")
        return payload

    async def _send_error(
        self, websocket: WebSocket, *, code: str, message: str, request_id: UUID | None = None
    ) -> None:
        payload: dict[str, str] = {"type": "chat.error.v1", "code": code, "message": message}
        if request_id is not None:
            payload["request_id"] = str(request_id)
        await websocket.send_json(payload)
