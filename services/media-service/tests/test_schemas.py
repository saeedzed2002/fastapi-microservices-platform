import pytest
from pydantic import ValidationError

from media_service.schemas import UploadRequest


def test_upload_request_normalizes_checksum() -> None:
    request = UploadRequest(
        purpose="product_image",
        content_type="image/png",
        size_bytes=1,
        checksum_sha256="A" * 64,
    )
    assert request.checksum_sha256 == "a" * 64


def test_upload_request_rejects_non_hex_checksum() -> None:
    with pytest.raises(ValidationError):
        UploadRequest(
            purpose="avatar",
            content_type="image/png",
            size_bytes=1,
            checksum_sha256="g" * 64,
        )
