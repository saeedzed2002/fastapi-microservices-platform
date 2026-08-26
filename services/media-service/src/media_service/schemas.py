from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ImagePurpose = Literal["avatar", "product_image", "chat_attachment"]
ImageContentType = Literal["image/jpeg", "image/png", "image/webp"]


class UploadRequest(BaseModel):
    purpose: ImagePurpose
    content_type: ImageContentType
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("checksum_sha256 must be hexadecimal")
        return normalized


class UploadAuthorization(BaseModel):
    asset_id: UUID
    upload_url: str
    expires_at: datetime


class DerivativeResponse(BaseModel):
    kind: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    download_url: str | None = None


class MediaAssetResponse(BaseModel):
    id: UUID
    purpose: str
    content_type: str
    size_bytes: int
    status: str
    processing_error: str | None
    created_at: datetime
    ready_at: datetime | None
    derivatives: list[DerivativeResponse] = Field(default_factory=list)


class InternalChatAttachmentDownloadRequest(BaseModel):
    subject_id: UUID
    conversation_id: UUID
    message_id: UUID
    expires_at: int = Field(gt=0)


class InternalChatAttachmentDownloadResponse(BaseModel):
    asset_id: UUID
    content_type: str
    size_bytes: int = Field(gt=0)
    download_url: str
