"""add saga reservations and reliable messaging"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_saga_reservations"
down_revision: str | Sequence[str] | None = "0001_inventory_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_reservations_order_id", "reservations", ["order_id"], unique=False)
    op.create_index("ix_reservations_status", "reservations", ["status"], unique=False)
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("inbox_messages")
    op.drop_index("ix_reservations_status", table_name="reservations")
    op.drop_index("ix_reservations_order_id", table_name="reservations")
    op.drop_table("reservations")
