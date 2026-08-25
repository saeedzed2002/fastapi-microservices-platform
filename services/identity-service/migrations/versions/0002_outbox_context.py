"""add outbox correlation and trace context"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_outbox_context"
down_revision: str | Sequence[str] | None = "0001_identity_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_messages",
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "outbox_messages",
        sa.Column("causation_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "outbox_messages",
        sa.Column("trace_id", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE outbox_messages "
            "SET correlation_id = event_id, trace_id = '00000000000000000000000000000000' "
            "WHERE correlation_id IS NULL OR trace_id IS NULL"
        )
    )
    op.alter_column("outbox_messages", "correlation_id", nullable=False)
    op.alter_column("outbox_messages", "trace_id", nullable=False)


def downgrade() -> None:
    op.drop_column("outbox_messages", "trace_id")
    op.drop_column("outbox_messages", "causation_id")
    op.drop_column("outbox_messages", "correlation_id")
