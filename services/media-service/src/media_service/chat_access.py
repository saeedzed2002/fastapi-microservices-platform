import hashlib
import hmac
import time
from uuid import UUID

from fastapi import HTTPException, status

from media_service.config import Settings


def _canonical_access_proof(
    *,
    subject_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    asset_id: UUID,
    expires_at: int,
) -> bytes:
    return "\n".join(
        (
            str(subject_id),
            str(conversation_id),
            str(message_id),
            str(asset_id),
            str(expires_at),
        )
    ).encode()


def verify_chat_access_proof(
    *,
    settings: Settings,
    provided_proof: str,
    subject_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    asset_id: UUID,
    expires_at: int,
) -> None:
    now = int(time.time())
    if expires_at <= now or expires_at > now + settings.chat_access_proof_max_ttl_seconds:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid chat access proof"
        )
    canonical = _canonical_access_proof(
        subject_id=subject_id,
        conversation_id=conversation_id,
        message_id=message_id,
        asset_id=asset_id,
        expires_at=expires_at,
    )
    secrets = [settings.chat_access_secret]
    if settings.chat_access_previous_secret is not None:
        secrets.append(settings.chat_access_previous_secret)
    for secret in secrets:
        expected_proof = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_proof, provided_proof):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid chat access proof")
