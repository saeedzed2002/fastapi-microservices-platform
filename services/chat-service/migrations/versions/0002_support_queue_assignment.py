"""add support queue assignment"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_support_queue_assignment"
down_revision: str | Sequence[str] | None = "0001_chat_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_conversations",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("customer_subject_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assigned_admin_subject_id", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'closed')",
            name="ck_support_conversations_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_support_conversations_customer_subject_id",
        "support_conversations",
        ["customer_subject_id"],
    )
    op.create_index("ix_support_conversations_status", "support_conversations", ["status"])
    op.create_index(
        "ix_support_conversations_assigned_admin_subject_id",
        "support_conversations",
        ["assigned_admin_subject_id"],
    )
    op.create_index(
        "uq_support_conversations_active_customer",
        "support_conversations",
        ["customer_subject_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'claimed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_support_conversations_active_customer", table_name="support_conversations")
    op.drop_index(
        "ix_support_conversations_assigned_admin_subject_id", table_name="support_conversations"
    )
    op.drop_index("ix_support_conversations_status", table_name="support_conversations")
    op.drop_index(
        "ix_support_conversations_customer_subject_id", table_name="support_conversations"
    )
    op.drop_table("support_conversations")
