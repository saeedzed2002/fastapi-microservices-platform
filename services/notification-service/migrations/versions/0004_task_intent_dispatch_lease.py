"""recover stale notification task dispatch claims"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_task_intent_dispatch_lease"
down_revision: str | Sequence[str] | None = "0003_sms_otp_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "task_intents",
        sa.Column("dispatch_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("task_intents", sa.Column("dispatch_claim_token", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_task_intents_dispatch_recovery",
        "task_intents",
        ["status", "dispatch_claimed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_intents_dispatch_recovery", table_name="task_intents")
    op.drop_column("task_intents", "dispatch_claim_token")
    op.drop_column("task_intents", "dispatch_claimed_at")
