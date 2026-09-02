import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from redis.exceptions import ConnectionError

from chat_service.config import Settings
from chat_service.realtime import ChatRealtime, ConnectionHub
from chat_service.schemas import MessageResponse


class FakeWebSocket:
    def __init__(self) -> None:
        self.frames: list[dict[str, object]] = []

    async def send_json(self, frame: dict[str, object]) -> None:
        self.frames.append(frame)


class FailingRedis:
    def __init__(self) -> None:
        self.closed = False

    async def incr(self, key: str) -> int:
        raise ConnectionError(f"Redis unavailable for {key}")

    async def aclose(self) -> None:
        self.closed = True


class CountingRedis:
    def __init__(self) -> None:
        self.increments: list[str] = []
        self.expirations: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        self.increments.append(key)
        return len(self.increments)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations.append((key, seconds))
        return True


def test_local_fanout_is_limited_to_message_participants() -> None:
    async def run() -> None:
        hub = ConnectionHub()
        recipient_id, unrelated_id = uuid4(), uuid4()
        recipient_socket, unrelated_socket = FakeWebSocket(), FakeWebSocket()
        hub.add(websocket=recipient_socket, subject_id=recipient_id)  # type: ignore[arg-type]
        hub.add(websocket=unrelated_socket, subject_id=unrelated_id)  # type: ignore[arg-type]
        message = MessageResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            client_message_id=uuid4(),
            sender_id=uuid4(),
            content="durable first",
            message_type="text",
            created_at=datetime.now(UTC),
        )

        await hub.broadcast(participant_ids=[recipient_id], message=message)

        assert recipient_socket.frames[0]["type"] == "chat.message.v1"
        assert unrelated_socket.frames == []

    asyncio.run(run())


def test_connection_rate_limit_is_fail_closed_without_redis() -> None:
    async def run() -> None:
        realtime = ChatRealtime(Settings(redis_enabled=False), ConnectionHub())
        assert not await realtime.allow_connection(remote_ip="127.0.0.1")

    asyncio.run(run())


def test_connection_rate_limit_reconnects_after_a_redis_restart() -> None:
    async def run() -> None:
        realtime = ChatRealtime(Settings(), ConnectionHub())
        failed_client = FailingRedis()
        replacement_client = CountingRedis()
        realtime._command_client = failed_client  # type: ignore[assignment]
        realtime._create_redis_client = lambda: replacement_client  # type: ignore[assignment, method-assign, return-value]

        assert await realtime.allow_connection(remote_ip="127.0.0.1")
        assert failed_client.closed
        assert replacement_client.increments == ["fastapi-platform:chat:ws-rate:v1:127.0.0.1"]
        assert replacement_client.expirations == [
            ("fastapi-platform:chat:ws-rate:v1:127.0.0.1", 60)
        ]

    asyncio.run(run())
