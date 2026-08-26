from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_by_subject_id: Mapped[UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "subject_id", name="uq_conversation_participants_subject"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[UUID] = mapped_column(index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_read_message_id: Mapped[UUID | None] = mapped_column(nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "content IS NULL OR length(btrim(content)) > 0", name="ck_messages_content_not_blank"
        ),
        CheckConstraint("message_type = 'text'", name="ck_messages_supported_type"),
        UniqueConstraint(
            "sender_subject_id", "client_message_id", name="uq_messages_sender_client"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender_subject_id: Mapped[UUID] = mapped_column(index=True)
    client_message_id: Mapped[UUID] = mapped_column()
    content: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_message_attachments_size_positive"),
        UniqueConstraint("message_id", "media_asset_id", name="uq_message_attachments_asset"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    media_asset_id: Mapped[UUID] = mapped_column(index=True)
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
