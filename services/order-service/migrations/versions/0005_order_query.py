"""add order query indexes and clean invalid email snapshots"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_order_query"
down_revision: str | Sequence[str] | None = "0004_outbox_publish_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE orders SET customer_email = NULL WHERE customer_email = 'None'")
    op.create_index(
        "ix_orders_customer_created_id",
        "orders",
        ["customer_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_orders_status_created_id",
        "orders",
        ["status", "created_at", "id"],
        unique=False,
    )
    op.create_index("ix_orders_created_id", "orders", ["created_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_orders_created_id", table_name="orders")
    op.drop_index("ix_orders_status_created_id", table_name="orders")
    op.drop_index("ix_orders_customer_created_id", table_name="orders")
