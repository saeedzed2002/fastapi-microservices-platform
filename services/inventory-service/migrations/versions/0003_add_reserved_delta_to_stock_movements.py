"""record stock reservation deltas in the inventory ledger"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_reserved_movement_delta"
down_revision: str | Sequence[str] | None = "0002_saga_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stock_movements",
        sa.Column("reserved_delta", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("stock_movements", "reserved_delta", server_default=None)


def downgrade() -> None:
    op.drop_column("stock_movements", "reserved_delta")
