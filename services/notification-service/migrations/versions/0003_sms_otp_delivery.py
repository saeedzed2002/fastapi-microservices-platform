"""add SMS OTP delivery state"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_sms_otp_delivery"
down_revision: str | Sequence[str] | None = "0002_delivery_processing_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sms_otp_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=320), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_otp_deliveries_phone", "sms_otp_deliveries", ["phone"])
    op.create_index("ix_sms_otp_deliveries_status", "sms_otp_deliveries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sms_otp_deliveries_status", table_name="sms_otp_deliveries")
    op.drop_index("ix_sms_otp_deliveries_phone", table_name="sms_otp_deliveries")
    op.drop_table("sms_otp_deliveries")
