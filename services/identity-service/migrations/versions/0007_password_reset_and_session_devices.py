"""add staff password reset state and device session metadata"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_password_reset_and_session_devices"
down_revision: str | Sequence[str] | None = "0006_two_role_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_sessions",
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.alter_column("refresh_sessions", "last_used_at", server_default=None)
    op.create_table(
        "password_reset_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_password_reset_requests_user_id",
        "password_reset_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_password_reset_requests_expires_at",
        "password_reset_requests",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_requests_expires_at", table_name="password_reset_requests")
    op.drop_index("ix_password_reset_requests_user_id", table_name="password_reset_requests")
    op.drop_table("password_reset_requests")
    op.drop_column("refresh_sessions", "last_used_at")
    op.drop_column("refresh_sessions", "ip_hash")
    op.drop_column("refresh_sessions", "user_agent")
