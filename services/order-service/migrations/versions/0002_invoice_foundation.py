"""add invoice workflow and delivery contact snapshot"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_invoice_foundation"
down_revision: str | Sequence[str] | None = "0001_order_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("customer_email", sa.String(length=320), nullable=True))
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=600), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_invoices_order_id", "invoices", ["order_id"], unique=False)
    op.create_index("ix_invoices_status", "invoices", ["status"], unique=False)
    op.create_table(
        "task_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_name", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_intents_status", "task_intents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_intents_status", table_name="task_intents")
    op.drop_table("task_intents")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_order_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_column("orders", "customer_email")
