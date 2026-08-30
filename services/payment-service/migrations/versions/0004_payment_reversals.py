"""record Zarinpal reversals durably"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_payment_reversals"
down_revision: str | Sequence[str] | None = "0003_zarinpal_payment_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_reversals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("refund_request_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("intent_id"),
        sa.UniqueConstraint("refund_request_id"),
    )
    op.create_index("ix_payment_reversals_attempt_id", "payment_reversals", ["attempt_id"])
    op.create_index("ix_payment_reversals_intent_id", "payment_reversals", ["intent_id"])
    op.create_index(
        "ix_payment_reversals_refund_request_id", "payment_reversals", ["refund_request_id"]
    )
    op.create_index("ix_payment_reversals_requested_by", "payment_reversals", ["requested_by"])
    op.create_index("ix_payment_reversals_status", "payment_reversals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payment_reversals_status", table_name="payment_reversals")
    op.drop_index("ix_payment_reversals_requested_by", table_name="payment_reversals")
    op.drop_index("ix_payment_reversals_intent_id", table_name="payment_reversals")
    op.drop_index("ix_payment_reversals_refund_request_id", table_name="payment_reversals")
    op.drop_index("ix_payment_reversals_attempt_id", table_name="payment_reversals")
    op.drop_table("payment_reversals")
