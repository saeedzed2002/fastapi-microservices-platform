"""add notification delivery processing lease"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_delivery_processing_lease"
down_revision: str | Sequence[str] | None = "0001_notification_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_deliveries", "processing_started_at")
