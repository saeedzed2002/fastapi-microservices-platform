"""add staff authentication audit events"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_staff_authentication_audit"
down_revision: str | Sequence[str] | None = "0004_phone_otp_customer_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "authentication_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_authentication_audit_events_target_occurred",
        "authentication_audit_events",
        ["target_user_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authentication_audit_events_target_occurred",
        table_name="authentication_audit_events",
    )
    op.drop_table("authentication_audit_events")
