from datetime import UTC, datetime
from uuid import uuid4

import pytest

from identity_service.models import OutboxMessage
from identity_service.workers.outbox_publisher import build_event_envelope


def test_build_event_envelope_uses_version_and_context() -> None:
    event_id = uuid4()
    aggregate_id = uuid4()
    correlation_id = uuid4()
    message = OutboxMessage(
        event_id=event_id,
        event_type="identity.user_registered.v1",
        aggregate_type="user",
        aggregate_id=aggregate_id,
        payload={
            "user_id": str(aggregate_id),
            "email": "customer@example.com",
            "roles": ["customer"],
        },
        correlation_id=correlation_id,
        trace_id="0123456789abcdef0123456789abcdef",
        occurred_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
    )

    envelope = build_event_envelope(message, producer="identity-service")

    assert envelope["event_id"] == str(event_id)
    assert envelope["event_version"] == 1
    assert envelope["aggregate_id"] == str(aggregate_id)
    assert envelope["correlation_id"] == str(correlation_id)
    assert envelope["occurred_at"] == "2026-08-25T09:00:00Z"


def test_build_event_envelope_rejects_unversioned_events() -> None:
    message = OutboxMessage(
        event_type="identity.user_registered",
        aggregate_type="user",
        aggregate_id=uuid4(),
        payload={},
        correlation_id=uuid4(),
        trace_id="0123456789abcdef0123456789abcdef",
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="version suffix"):
        build_event_envelope(message, producer="identity-service")
