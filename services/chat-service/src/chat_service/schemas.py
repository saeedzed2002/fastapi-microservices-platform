from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ConversationCreate(BaseModel):
    participant_ids: list[UUID] = Field(min_length=1, max_length=24)


class AttachmentResponse(BaseModel):
    asset_id: UUID
    content_type: str
    size_bytes: int


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    client_message_id: UUID
    sender_id: UUID
    content: str | None
    message_type: str
    created_at: datetime
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: UUID
    participant_ids: list[UUID]
    created_by_subject_id: UUID
    created_at: datetime
    last_message_at: datetime | None
    unread_count: int


class ConversationPage(BaseModel):
    items: list[ConversationResponse]


class MessagePage(BaseModel):
    items: list[MessageResponse]
    next_before: str | None = None
    next_after: str | None = None


class MarkReadRequest(BaseModel):
    message_id: UUID


class MarkReadResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    read_at: datetime


class PresenceResponse(BaseModel):
    subject_id: UUID
    status: Literal["online", "offline", "unknown"]


class AttachmentDownloadResponse(BaseModel):
    asset_id: UUID
    content_type: str
    size_bytes: int
    download_url: str


class MediaAssetResponse(BaseModel):
    id: UUID
    purpose: str
    content_type: str
    size_bytes: int
    status: str


class MediaAttachment(BaseModel):
    asset_id: UUID
    content_type: str
    size_bytes: int


class AuthenticateFrame(BaseModel):
    type: Literal["chat.authenticate.v1"]
    request_id: UUID
    access_token: str = Field(min_length=1, max_length=8192)


class SendMessageFrame(BaseModel):
    type: Literal["chat.send_message.v1"]
    request_id: UUID
    client_message_id: UUID
    conversation_id: UUID
    content: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[UUID] = Field(max_length=8)

    @model_validator(mode="after")
    def validate_content_or_attachments(self) -> SendMessageFrame:
        if self.content is not None:
            normalized_content = self.content.strip()
            self.content = normalized_content or None
        if self.content is None and not self.attachment_ids:
            raise ValueError("content or attachment_ids is required")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("attachment_ids must be unique")
        return self


class HeartbeatFrame(BaseModel):
    type: Literal["chat.heartbeat.v1"]
    request_id: UUID
