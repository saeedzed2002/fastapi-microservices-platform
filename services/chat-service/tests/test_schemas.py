import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from chat_service.application import decode_cursor, encode_cursor
from chat_service.media import build_media_access_proof
from chat_service.schemas import SendMessageFrame


def test_chat_protocol_example_matches_canonical_schema() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (repository_root / "contracts/realtime/chat.v1.schema.json").read_text(encoding="utf-8")
    )
    example = json.loads(
        (repository_root / "contracts/realtime/chat.v1.example.json").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
        example
    )


def test_send_frame_requires_content_or_attachment() -> None:
    with pytest.raises(ValidationError):
        SendMessageFrame(
            type="chat.send_message.v1",
            request_id=uuid4(),
            client_message_id=uuid4(),
            conversation_id=uuid4(),
        )


def test_cursor_round_trip_is_stable() -> None:
    created_at = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    message_id = uuid4()

    assert decode_cursor(encode_cursor(created_at=created_at, message_id=message_id)) == (
        created_at,
        message_id,
    )


def test_media_access_proof_has_a_stable_canonical_payload() -> None:
    subject_id, conversation_id, message_id, asset_id = (uuid4(), uuid4(), uuid4(), uuid4())
    expires_at = 1_800_000_000
    secret = "test-chat-media-access-secret-at-least-32-bytes"
    canonical = "\n".join(
        map(str, (subject_id, conversation_id, message_id, asset_id, expires_at))
    ).encode()
    expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()

    assert (
        build_media_access_proof(
            secret=secret,
            subject_id=subject_id,
            conversation_id=conversation_id,
            message_id=message_id,
            asset_id=asset_id,
            expires_at=expires_at,
        )
        == expected
    )
