"""add Zarinpal payment workflow state"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_zarinpal_payment_workflow"
down_revision: str | Sequence[str] | None = "0002_outbox_publish_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_intents", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_payment_intents_expires_at", "payment_intents", ["expires_at"])
    op.add_column(
        "payment_attempts",
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="fake"),
    )
    op.alter_column("payment_attempts", "provider", server_default=None)
    op.add_column("payment_attempts", sa.Column("authority", sa.String(length=64), nullable=True))
    op.add_column(
        "payment_attempts", sa.Column("reference_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "payment_attempts", sa.Column("failure_code", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint("uq_payment_attempts_authority", "payment_attempts", ["authority"])


def downgrade() -> None:
    op.drop_constraint("uq_payment_attempts_authority", "payment_attempts", type_="unique")
    op.drop_column("payment_attempts", "failure_code")
    op.drop_column("payment_attempts", "reference_id")
    op.drop_column("payment_attempts", "authority")
    op.drop_column("payment_attempts", "provider")
    op.drop_index("ix_payment_intents_expires_at", table_name="payment_intents")
    op.drop_column("payment_intents", "expires_at")
