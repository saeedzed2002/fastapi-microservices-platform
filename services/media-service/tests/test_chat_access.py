import hashlib
import hmac
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

from media_service.chat_access import verify_chat_access_proof
from media_service.config import Settings


def _proof(
    *,
    secret: str,
    subject_id: str,
    conversation_id: str,
    message_id: str,
    asset_id: str,
    expires_at: int,
) -> str:
    canonical = "\n".join(
        (subject_id, conversation_id, message_id, asset_id, str(expires_at))
    ).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def test_chat_access_proof_accepts_current_secret() -> None:
    subject_id, conversation_id, message_id, asset_id = (uuid4(), uuid4(), uuid4(), uuid4())
    settings = Settings(chat_access_secret="test-chat-media-access-secret-at-least-32-bytes")
    expires_at = int(time.time()) + 30

    verify_chat_access_proof(
        settings=settings,
        provided_proof=_proof(
            secret=settings.chat_access_secret,
            subject_id=str(subject_id),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            asset_id=str(asset_id),
            expires_at=expires_at,
        ),
        subject_id=subject_id,
        conversation_id=conversation_id,
        message_id=message_id,
        asset_id=asset_id,
        expires_at=expires_at,
    )


def test_chat_access_proof_rejects_expired_proof() -> None:
    subject_id, conversation_id, message_id, asset_id = (uuid4(), uuid4(), uuid4(), uuid4())
    settings = Settings(chat_access_secret="test-chat-media-access-secret-at-least-32-bytes")

    with pytest.raises(HTTPException) as exc_info:
        verify_chat_access_proof(
            settings=settings,
            provided_proof="invalid",
            subject_id=subject_id,
            conversation_id=conversation_id,
            message_id=message_id,
            asset_id=asset_id,
            expires_at=int(time.time()) - 1,
        )

    assert exc_info.value.status_code == 403
