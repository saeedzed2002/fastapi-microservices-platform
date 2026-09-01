"""add post-delivery return and refund correlation records"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_post_delivery_returns"
down_revision: str | Sequence[str] | None = "0007_fulfillment_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_return_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("received_by", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'RECEIVED', "
            "'REFUND_PENDING', 'REFUNDED', 'REFUND_FAILED')",
            name="ck_order_return_requests_status",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_idempotency_key"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("receipt_idempotency_key"),
    )
    op.create_index("ix_order_return_requests_decided_by", "order_return_requests", ["decided_by"])
    op.create_index("ix_order_return_requests_order_id", "order_return_requests", ["order_id"])
    op.create_index(
        "ix_order_return_requests_received_by", "order_return_requests", ["received_by"]
    )
    op.create_index(
        "ix_order_return_requests_requested_by", "order_return_requests", ["requested_by"]
    )
    op.create_index("ix_order_return_requests_status", "order_return_requests", ["status"])
    op.add_column("order_refund_requests", sa.Column("return_request_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_refund_requests", sa.Column("pre_refund_status", sa.String(length=32), nullable=True)
    )
    op.create_unique_constraint(
        "uq_order_refund_requests_return_request_id",
        "order_refund_requests",
        ["return_request_id"],
    )
    op.create_foreign_key(
        "fk_order_refund_requests_return_request_id",
        "order_refund_requests",
        "order_return_requests",
        ["return_request_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_order_refund_requests_return_request_id",
        "order_refund_requests",
        ["return_request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_order_refund_requests_return_request_id", table_name="order_refund_requests")
    op.drop_constraint(
        "fk_order_refund_requests_return_request_id",
        "order_refund_requests",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_order_refund_requests_return_request_id",
        "order_refund_requests",
        type_="unique",
    )
    op.drop_column("order_refund_requests", "pre_refund_status")
    op.drop_column("order_refund_requests", "return_request_id")
    op.drop_index("ix_order_return_requests_status", table_name="order_return_requests")
    op.drop_index("ix_order_return_requests_requested_by", table_name="order_return_requests")
    op.drop_index("ix_order_return_requests_received_by", table_name="order_return_requests")
    op.drop_index("ix_order_return_requests_order_id", table_name="order_return_requests")
    op.drop_index("ix_order_return_requests_decided_by", table_name="order_return_requests")
    op.drop_table("order_return_requests")
