"""add durable outbox publication claim"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_outbox_publish_claim"
down_revision: str | Sequence[str] | None = "0001_media_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_messages", sa.Column("publish_claim_token", sa.Uuid(), nullable=True))
    op.add_column(
        "outbox_messages",
        sa.Column("publish_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_messages_publication_claim",
        "outbox_messages",
        ["published_at", "publish_claimed_at", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_publication_claim", table_name="outbox_messages")
    op.drop_column("outbox_messages", "publish_claimed_at")
    op.drop_column("outbox_messages", "publish_claim_token")
