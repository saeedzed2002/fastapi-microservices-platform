import hashlib
import hmac
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

from media_service.catalog_access import verify_catalog_access_proof
from media_service.config import Settings


def test_catalog_access_proof_accepts_the_current_secret() -> None:
    subject_id, asset_id = uuid4(), uuid4()
    settings = Settings(catalog_access_secret="test-catalog-media-access-secret-at-least-32-bytes")
    expires_at = int(time.time()) + 30
    canonical = "\n".join((str(subject_id), str(asset_id), str(expires_at))).encode()
    proof = hmac.new(settings.catalog_access_secret.encode(), canonical, hashlib.sha256).hexdigest()

    verify_catalog_access_proof(
        settings=settings,
        provided_proof=proof,
        subject_id=subject_id,
        asset_id=asset_id,
        expires_at=expires_at,
    )


def test_catalog_access_proof_rejects_an_invalid_proof() -> None:
    settings = Settings(catalog_access_secret="test-catalog-media-access-secret-at-least-32-bytes")

    with pytest.raises(HTTPException) as exc_info:
        verify_catalog_access_proof(
            settings=settings,
            provided_proof="invalid",
            subject_id=uuid4(),
            asset_id=uuid4(),
            expires_at=int(time.time()) + 30,
        )

    assert exc_info.value.status_code == 403
