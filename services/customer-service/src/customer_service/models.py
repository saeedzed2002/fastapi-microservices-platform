from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
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


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_media_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (Index("ix_addresses_customer_id", "customer_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(64))
    recipient_name: Mapped[str] = mapped_column(String(120))
    line1: Mapped[str] = mapped_column(String(240))
    line2: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str] = mapped_column(String(120))
    postal_code: Mapped[str] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
