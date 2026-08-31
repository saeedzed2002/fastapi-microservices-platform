"""add durable staff password-reset email deliveries"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_password_reset_delivery"
down_revision: str | Sequence[str] | None = "0004_task_intent_dispatch_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_email_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=320), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_email_deliveries_recipient_email",
        "password_reset_email_deliveries",
        ["recipient_email"],
    )
    op.create_index(
        "ix_password_reset_email_deliveries_status",
        "password_reset_email_deliveries",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_email_deliveries_status",
        table_name="password_reset_email_deliveries",
    )
    op.drop_index(
        "ix_password_reset_email_deliveries_recipient_email",
        table_name="password_reset_email_deliveries",
    )
    op.drop_table("password_reset_email_deliveries")
