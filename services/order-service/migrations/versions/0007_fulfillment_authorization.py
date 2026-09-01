"""add the refund-safe fulfillment authorization fence"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_fulfillment_authorization"
down_revision: str | Sequence[str] | None = "0006_order_fulfillment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fulfillment_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("target_status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CONSUMED', 'EXPIRED', 'RELEASED')",
            name="ck_fulfillment_authorizations_status",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_fulfillment_authorizations_expiry",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id"),
    )
    op.create_index(
        "uq_fulfillment_authorizations_active_order",
        "fulfillment_authorizations",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_fulfillment_authorizations_expires_at",
        "fulfillment_authorizations",
        ["expires_at"],
    )
    op.create_index(
        "ix_fulfillment_authorizations_order_id",
        "fulfillment_authorizations",
        ["order_id"],
    )
    op.create_index(
        "ix_fulfillment_authorizations_requested_by",
        "fulfillment_authorizations",
        ["requested_by"],
    )
    op.create_index(
        "ix_fulfillment_authorizations_status",
        "fulfillment_authorizations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_fulfillment_authorizations_status", table_name="fulfillment_authorizations")
    op.drop_index(
        "ix_fulfillment_authorizations_requested_by", table_name="fulfillment_authorizations"
    )
    op.drop_index("ix_fulfillment_authorizations_order_id", table_name="fulfillment_authorizations")
    op.drop_index(
        "ix_fulfillment_authorizations_expires_at", table_name="fulfillment_authorizations"
    )
    op.drop_index(
        "uq_fulfillment_authorizations_active_order", table_name="fulfillment_authorizations"
    )
    op.drop_table("fulfillment_authorizations")
