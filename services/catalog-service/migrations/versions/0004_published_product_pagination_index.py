"""index published Catalog pagination order"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_product_page_index"
down_revision: str | Sequence[str] | None = "0003_search_events_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_products_published_page",
        "products",
        ["status", "published_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_products_published_page", table_name="products")
