from datetime import UTC, datetime
from uuid import uuid4

from media_service.models import OutboxMessage
from media_service.workers.outbox_publisher import build_event_envelope


def test_media_event_has_versioned_envelope() -> None:
    message = OutboxMessage(
        event_type="media.ready.v1",
        aggregate_type="media_asset",
        aggregate_id=uuid4(),
        payload={"media_asset_id": str(uuid4())},
        occurred_at=datetime.now(UTC),
    )
    envelope = build_event_envelope(message, producer="media-service")
    assert envelope["event_type"] == "media.ready.v1"
    assert envelope["event_version"] == 1
