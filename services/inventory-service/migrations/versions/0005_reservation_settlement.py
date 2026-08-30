"""record committed and returned inventory reservations"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reservation_settlement"
down_revision: str | Sequence[str] | None = "0004_outbox_publish_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reservations", sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reservations", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reservations", "returned_at")
    op.drop_column("reservations", "committed_at")
