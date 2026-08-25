"""add invoice processing lease"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_invoice_processing_lease"
down_revision: str | Sequence[str] | None = "0002_invoice_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoices", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("invoices", "processing_started_at")
