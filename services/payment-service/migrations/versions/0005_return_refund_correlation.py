"""persist post-delivery return correlation on payment reversals"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_return_refund_correlation"
down_revision: str | Sequence[str] | None = "0004_payment_reversals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payment_reversals", sa.Column("return_request_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_payment_reversals_return_request_id", "payment_reversals", ["return_request_id"]
    )
    op.create_index(
        "ix_payment_reversals_return_request_id", "payment_reversals", ["return_request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_payment_reversals_return_request_id", table_name="payment_reversals")
    op.drop_constraint(
        "uq_payment_reversals_return_request_id", "payment_reversals", type_="unique"
    )
    op.drop_column("payment_reversals", "return_request_id")
