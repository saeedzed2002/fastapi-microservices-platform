"""Kafka poison-record handling with an inspectable, durable dead-letter record."""

import asyncio
import base64
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from aiokafka.structs import OffsetAndMetadata, TopicPartition  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class KafkaConsumerProtocol(Protocol):
    async def commit(
        self, offsets: Mapping[TopicPartition, OffsetAndMetadata] | None = None
    ) -> None: ...


class KafkaProducerProtocol(Protocol):
    async def send_and_wait(
        self,
        topic: str,
        value: bytes | None = None,
        key: bytes | None = None,
        **kwargs: Any,
    ) -> Any: ...


class KafkaRecordProtocol(Protocol):
    topic: str
    partition: int
    offset: int
    timestamp: int
    key: bytes | None
    value: bytes | None
    headers: list[tuple[str, bytes | None]]


@dataclass(frozen=True)
class KafkaDlqPolicy:
    """Consumer-specific retry and dead-letter settings.

    Attempts are intentionally local to one processing session. A successful DLQ
    publish is durable in Kafka; an unavailable DLQ prevents a source-offset
    commit, so the source record remains recoverable after a restart.
    """

    consumer_name: str
    dead_letter_topic: str
    max_attempts: int
    retry_backoff_seconds: float
    dead_letter_retry_backoff_seconds: float = 1.0


@dataclass(frozen=True)
class FailureAttempt:
    attempt: int
    occurred_at: str
    exception_type: str
    reason: str


async def process_record_with_dead_letter(
    *,
    consumer: KafkaConsumerProtocol,
    producer: KafkaProducerProtocol,
    record: KafkaRecordProtocol,
    policy: KafkaDlqPolicy,
    handler: Callable[[], Awaitable[None]],
    stop: asyncio.Event,
) -> bool:
    """Process one record, retry it, or durably move it to the Kafka DLQ.

    Returns ``True`` only when the source offset was committed. A ``False``
    result means shutdown interrupted handling and the source record remains
    uncommitted. A DLQ broker failure deliberately blocks the current record;
    it must never be skipped in favour of a later record.
    """

    if policy.max_attempts < 1:
        raise ValueError("Kafka DLQ policy max_attempts must be at least one")
    if stop.is_set():
        return False

    failures: list[FailureAttempt] = []
    for attempt in range(1, policy.max_attempts + 1):
        if stop.is_set():
            return False
        try:
            await handler()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = FailureAttempt(
                attempt=attempt,
                occurred_at=_utc_now(),
                exception_type=type(exc).__name__,
                reason=str(exc)[:2000],
            )
            failures.append(failure)
            logger.warning(
                "kafka_record_processing_failed",
                extra={
                    "consumer_name": policy.consumer_name,
                    "source_topic": record.topic,
                    "source_partition": record.partition,
                    "source_offset": record.offset,
                    "attempt": attempt,
                    "max_attempts": policy.max_attempts,
                    "exception_type": failure.exception_type,
                },
            )
            if attempt < policy.max_attempts:
                if await _wait_for_stop(stop, policy.retry_backoff_seconds * (2 ** (attempt - 1))):
                    return False
                continue
        else:
            await _commit_record(consumer, record)
            return True
        break

    dead_letter = _build_dead_letter(record, policy, failures)
    dead_letter_key = f"{record.topic}:{record.partition}:{record.offset}".encode()
    while not stop.is_set():
        try:
            await producer.send_and_wait(
                policy.dead_letter_topic,
                key=dead_letter_key,
                value=json.dumps(dead_letter, separators=(",", ":")).encode(),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "kafka_dead_letter_publish_failed",
                extra={
                    "consumer_name": policy.consumer_name,
                    "dead_letter_topic": policy.dead_letter_topic,
                    "source_topic": record.topic,
                    "source_partition": record.partition,
                    "source_offset": record.offset,
                },
            )
            await _wait_for_stop(stop, policy.dead_letter_retry_backoff_seconds)
            continue

        await _commit_record(consumer, record)
        logger.error(
            "kafka_record_dead_lettered",
            extra={
                "consumer_name": policy.consumer_name,
                "dead_letter_topic": policy.dead_letter_topic,
                "source_topic": record.topic,
                "source_partition": record.partition,
                "source_offset": record.offset,
                "attempts": len(failures),
            },
        )
        return True
    return False


async def _commit_record(consumer: KafkaConsumerProtocol, record: KafkaRecordProtocol) -> None:
    """Commit exactly this source record, never a prefetched later record."""

    source_partition = TopicPartition(record.topic, record.partition)
    await consumer.commit({source_partition: OffsetAndMetadata(record.offset + 1, "")})


async def _wait_for_stop(stop: asyncio.Event, seconds: float) -> bool:
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(seconds, 0))
    except TimeoutError:
        return False
    return True


def _build_dead_letter(
    record: KafkaRecordProtocol,
    policy: KafkaDlqPolicy,
    failures: list[FailureAttempt],
) -> dict[str, object]:
    event_context = _event_context(record.value)
    return {
        "dead_letter_version": 1,
        "dead_lettered_at": _utc_now(),
        "consumer": {"name": policy.consumer_name},
        "source": {
            "topic": record.topic,
            "partition": record.partition,
            "offset": record.offset,
            "timestamp_ms": record.timestamp,
            "key_base64": _base64(record.key),
            "value_base64": _base64(record.value),
            "headers": [
                {"name": name, "value_base64": _base64(value)} for name, value in record.headers
            ],
        },
        "event_context": event_context,
        "failure_history": [asdict(failure) for failure in failures],
    }


def _event_context(value: bytes | None) -> dict[str, str | None]:
    empty: dict[str, str | None] = {
        "event_id": None,
        "event_type": None,
        "correlation_id": None,
        "causation_id": None,
        "trace_id": None,
    }
    if value is None:
        return empty
    try:
        payload = json.loads(value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return empty
    if not isinstance(payload, dict):
        return empty
    return {
        field: payload.get(field) if isinstance(payload.get(field), str) else None
        for field in empty
    }


def _base64(value: bytes | None) -> str | None:
    return base64.b64encode(value).decode() if value is not None else None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
