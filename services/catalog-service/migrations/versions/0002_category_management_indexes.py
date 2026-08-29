"""category management indexes"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_category_management_indexes"
down_revision: str | Sequence[str] | None = "0001_catalog_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_categories_parent_id", table_name="categories")
