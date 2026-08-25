from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    tracking_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    delivery_address: Mapped[dict[str, str]] = mapped_column(JSON)
    payment_method: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    variant_id: Mapped[UUID] = mapped_column(index=True)
    sku: Mapped[str] = mapped_column(String(100))
    product_name: Mapped[str] = mapped_column(String(240))
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)


class OrderStateTransition(Base):
    __tablename__ = "order_state_transitions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[UUID | None] = mapped_column(unique=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(160))
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID] = mapped_column(index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[UUID] = mapped_column()
    causation_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
