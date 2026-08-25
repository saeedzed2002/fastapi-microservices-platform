"""order foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_order_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("tracking_code", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("delivery_address", sa.JSON(), nullable=False),
        sa.Column("payment_method", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tracking_code"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("unit_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_table(
        "order_state_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("event_id", sa.Uuid()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_order_state_transitions_order_id", "order_state_transitions", ["order_id"])
    for table in ("inbox_messages", "outbox_messages"):
        if table == "inbox_messages":
            op.create_table(
                table,
                sa.Column("id", sa.Uuid(), primary_key=True),
                sa.Column("event_id", sa.Uuid(), nullable=False),
                sa.Column("event_type", sa.String(160), nullable=False),
                sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
                sa.UniqueConstraint("event_id"),
            )
        else:
            op.create_table(
                table,
                sa.Column("id", sa.Uuid(), primary_key=True),
                sa.Column("event_id", sa.Uuid(), nullable=False),
                sa.Column("event_type", sa.String(160), nullable=False),
                sa.Column("aggregate_type", sa.String(80), nullable=False),
                sa.Column("aggregate_id", sa.Uuid(), nullable=False),
                sa.Column("payload", sa.JSON(), nullable=False),
                sa.Column("headers", sa.JSON(), nullable=False),
                sa.Column("correlation_id", sa.Uuid(), nullable=False),
                sa.Column("causation_id", sa.Uuid()),
                sa.Column("trace_id", sa.String(32), nullable=False),
                sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("published_at", sa.DateTime(timezone=True)),
                sa.Column("attempts", sa.Integer(), nullable=False),
                sa.Column("last_error", sa.Text()),
                sa.UniqueConstraint("event_id"),
            )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("inbox_messages")
    op.drop_index("ix_order_state_transitions_order_id", table_name="order_state_transitions")
    op.drop_table("order_state_transitions")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
