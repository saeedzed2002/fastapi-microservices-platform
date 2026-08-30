from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Computed, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SearchDocument(Base):
    __tablename__ = "search_documents"

    product_id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(260), unique=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    brand_id: Mapped[UUID | None] = mapped_column(index=True)
    category_id: Mapped[UUID | None] = mapped_column(index=True)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), index=True)
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(slug, '') "
            "|| ' ' || coalesce(description, ''))",
            persisted=True,
        ),
    )


class SearchTombstone(Base):
    __tablename__ = "search_tombstones"

    product_id: Mapped[UUID] = mapped_column(primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(160), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
