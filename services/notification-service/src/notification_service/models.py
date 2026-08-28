from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(unique=True, index=True)
    recipient_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(320))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SmsOtpDelivery(Base):
    __tablename__ = "sms_otp_deliveries"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(320))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TaskIntent(Base):
    __tablename__ = "task_intents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_name: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    dispatch_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_claim_token: Mapped[UUID | None] = mapped_column()
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
