from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_subject_id: Mapped[UUID] = mapped_column(index=True)
    purpose: Mapped[str] = mapped_column(String(48))
    original_object_key: Mapped[str] = mapped_column(String(600), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column()
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    processing_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaDerivative(Base):
    __tablename__ = "media_derivatives"
    __table_args__ = (UniqueConstraint("media_asset_id", "kind"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    media_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(48))
    object_key: Mapped[str] = mapped_column(String(600), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column()
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column()
    height: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MediaTaskIntent(Base):
    __tablename__ = "media_task_intents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_name: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(160))
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID] = mapped_column(index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(default=uuid4)
    causation_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str] = mapped_column(String(32), default=lambda: uuid4().hex)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
