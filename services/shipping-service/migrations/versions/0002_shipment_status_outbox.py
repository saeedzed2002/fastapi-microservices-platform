"""add shipment transition audit and outbox"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_shipment_status_outbox"
down_revision: str | Sequence[str] | None = "0001_shipment_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipment_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("target_status", sa.String(length=32), nullable=False),
        sa.Column("carrier", sa.String(length=120), nullable=True),
        sa.Column("tracking_number", sa.String(length=160), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_status IN ('READY', 'PROCESSING', 'SHIPPED')",
            name="ck_shipment_transitions_from_status",
        ),
        sa.CheckConstraint(
            "target_status IN ('PROCESSING', 'SHIPPED', 'DELIVERED')",
            name="ck_shipment_transitions_target_status",
        ),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("authorization_id"),
        sa.UniqueConstraint("command_id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_shipment_transitions_order_id", "shipment_transitions", ["order_id"])
    op.create_index(
        "ix_shipment_transitions_requested_by", "shipment_transitions", ["requested_by"]
    )
    op.create_index("ix_shipment_transitions_shipment_id", "shipment_transitions", ["shipment_id"])
    op.create_index(
        "ix_shipment_transitions_target_status", "shipment_transitions", ["target_status"]
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
        sa.Column("publish_claim_token", sa.Uuid(), nullable=True),
        sa.Column("publish_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_index("ix_shipment_transitions_target_status", table_name="shipment_transitions")
    op.drop_index("ix_shipment_transitions_shipment_id", table_name="shipment_transitions")
    op.drop_index("ix_shipment_transitions_requested_by", table_name="shipment_transitions")
    op.drop_index("ix_shipment_transitions_order_id", table_name="shipment_transitions")
    op.drop_table("shipment_transitions")
