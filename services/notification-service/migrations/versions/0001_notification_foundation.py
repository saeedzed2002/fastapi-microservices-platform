"""notification foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_notification_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=320), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id"),
    )
    op.create_index(
        "ix_notification_deliveries_invoice_id", "notification_deliveries", ["invoice_id"]
    )
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["status"])
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
    op.create_index("ix_task_intents_status", "task_intents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_task_intents_status", table_name="task_intents")
    op.drop_table("task_intents")
    op.drop_index("ix_notification_deliveries_status", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_invoice_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_table("inbox_messages")
