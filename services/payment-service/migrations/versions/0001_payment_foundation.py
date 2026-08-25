"""payment foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_payment_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("provider_reference"),
    )
    op.create_index("ix_payment_intents_order_id", "payment_intents", ["order_id"])
    op.create_index("ix_payment_intents_status", "payment_intents", ["status"])
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_attempts_intent_id", "payment_attempts", ["intent_id"])
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_table(
        "outbox_messages",
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
    op.drop_index("ix_payment_attempts_intent_id", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index("ix_payment_intents_status", table_name="payment_intents")
    op.drop_index("ix_payment_intents_order_id", table_name="payment_intents")
    op.drop_table("payment_intents")
