"""add administrator-managed order fulfillment"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_order_fulfillment"
down_revision: str | Sequence[str] | None = "0005_order_query"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_fulfillments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("carrier", sa.String(length=120), nullable=True),
        sa.Column("tracking_number", sa.String(length=160), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_order_fulfillments_order_id", "order_fulfillments", ["order_id"])
    op.create_index("ix_order_fulfillments_updated_by", "order_fulfillments", ["updated_by"])
    op.create_table(
        "order_refund_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_order_refund_requests_order_id", "order_refund_requests", ["order_id"])
    op.create_index(
        "ix_order_refund_requests_requested_by", "order_refund_requests", ["requested_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_refund_requests_requested_by", table_name="order_refund_requests")
    op.drop_index("ix_order_refund_requests_order_id", table_name="order_refund_requests")
    op.drop_table("order_refund_requests")
    op.drop_index("ix_order_fulfillments_updated_by", table_name="order_fulfillments")
    op.drop_index("ix_order_fulfillments_order_id", table_name="order_fulfillments")
    op.drop_table("order_fulfillments")
