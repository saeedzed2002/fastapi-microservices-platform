import asyncio
import base64
import json
from dataclasses import dataclass, field
from typing import Any

from platform_messaging.kafka_dlq import KafkaDlqPolicy, process_record_with_dead_letter


@dataclass
class FakeRecord:
    topic: str = "fastapi-platform.order.events.v1"
    partition: int = 2
    offset: int = 7
    timestamp: int = 1_762_000_000_000
    key: bytes | None = b"order-123"
    value: bytes | None = (
        b'{"event_id":"evt-1","event_type":"order.created.v1","correlation_id":"corr-1","causation_id":null,"trace_id":"trace-1"}'
    )
    headers: list[tuple[str, bytes | None]] = field(
        default_factory=lambda: [("traceparent", b"00-trace")]
    )


class FakeConsumer:
    def __init__(self) -> None:
        self.commits: list[Any] = []

    async def commit(self, offsets: Any = None) -> None:
        self.commits.append(offsets)


class FakeProducer:
    def __init__(self, *, fail: bool = False, stop: asyncio.Event | None = None) -> None:
        self.fail = fail
        self.stop = stop
        self.sent: list[dict[str, Any]] = []

    async def send_and_wait(
        self, topic: str, value: bytes | None = None, key: bytes | None = None, **_: Any
    ) -> None:
        self.sent.append({"topic": topic, "value": value, "key": key})
        if self.fail:
            assert self.stop is not None
            self.stop.set()
            raise RuntimeError("DLQ broker unavailable")


def policy() -> KafkaDlqPolicy:
    return KafkaDlqPolicy(
        consumer_name="order-service.saga",
        dead_letter_topic="fastapi-platform.dead-letter.v1",
        max_attempts=3,
        retry_backoff_seconds=0,
        dead_letter_retry_backoff_seconds=0,
    )


def test_successful_record_commits_exact_source_offset() -> None:
    asyncio.run(_test_successful_record_commits_exact_source_offset())


async def _test_successful_record_commits_exact_source_offset() -> None:
    consumer = FakeConsumer()
    producer = FakeProducer()

    committed = await process_record_with_dead_letter(
        consumer=consumer,
        producer=producer,
        record=FakeRecord(),
        policy=policy(),
        handler=lambda: _succeeds(),
        stop=asyncio.Event(),
    )

    assert committed is True
    assert len(consumer.commits) == 1
    assert producer.sent == []
    committed_offset = next(iter(consumer.commits[0].values()))
    assert committed_offset.offset == 8


def test_poison_record_is_dead_lettered_before_source_offset_commit() -> None:
    asyncio.run(_test_poison_record_is_dead_lettered_before_source_offset_commit())


async def _test_poison_record_is_dead_lettered_before_source_offset_commit() -> None:
    consumer = FakeConsumer()
    producer = FakeProducer()
    attempts = 0

    async def poison_handler() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid state transition")

    committed = await process_record_with_dead_letter(
        consumer=consumer,
        producer=producer,
        record=FakeRecord(),
        policy=policy(),
        handler=poison_handler,
        stop=asyncio.Event(),
    )

    assert committed is True
    assert attempts == 3
    assert len(consumer.commits) == 1
    assert producer.sent[0]["topic"] == "fastapi-platform.dead-letter.v1"
    assert producer.sent[0]["key"] == b"fastapi-platform.order.events.v1:2:7"
    dead_letter = json.loads(producer.sent[0]["value"])
    assert dead_letter["source"]["offset"] == 7
    assert base64.b64decode(dead_letter["source"]["value_base64"]) == FakeRecord().value
    assert dead_letter["event_context"]["event_type"] == "order.created.v1"
    assert [item["attempt"] for item in dead_letter["failure_history"]] == [1, 2, 3]


def test_unavailable_dlq_leaves_source_offset_uncommitted() -> None:
    asyncio.run(_test_unavailable_dlq_leaves_source_offset_uncommitted())


async def _test_unavailable_dlq_leaves_source_offset_uncommitted() -> None:
    consumer = FakeConsumer()
    stop = asyncio.Event()
    producer = FakeProducer(fail=True, stop=stop)

    async def poison_handler() -> None:
        raise ValueError("invalid state transition")

    committed = await process_record_with_dead_letter(
        consumer=consumer,
        producer=producer,
        record=FakeRecord(),
        policy=KafkaDlqPolicy(
            consumer_name="order-service.saga",
            dead_letter_topic="fastapi-platform.dead-letter.v1",
            max_attempts=1,
            retry_backoff_seconds=0,
            dead_letter_retry_backoff_seconds=0,
        ),
        handler=poison_handler,
        stop=stop,
    )

    assert committed is False
    assert consumer.commits == []


async def _succeeds() -> None:
    return None
