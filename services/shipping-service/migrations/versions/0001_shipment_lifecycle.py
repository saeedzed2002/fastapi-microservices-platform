"""create the Shipping-owned shipment lifecycle"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_shipment_lifecycle"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("carrier", sa.String(length=120), nullable=True),
        sa.Column("tracking_number", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('READY', 'PROCESSING', 'SHIPPED', 'DELIVERED')",
            name="ck_shipments_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_status", "shipments", ["status"])
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_inbox_messages_event_type", "inbox_messages", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_inbox_messages_event_type", table_name="inbox_messages")
    op.drop_table("inbox_messages")
    op.drop_index("ix_shipments_status", table_name="shipments")
    op.drop_index("ix_shipments_order_id", table_name="shipments")
    op.drop_table("shipments")
