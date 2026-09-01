"""add catalog archive state and product-media uniqueness

Revision ID: 0006_catalog_management
Revises: 0005_product_review_moderation
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_catalog_management"
down_revision: str | Sequence[str] | None = "0005_product_review_moderation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_products_admin_page", "products", ["status", "updated_at", "id"])
    op.create_unique_constraint(
        "uq_product_media_product_asset",
        "product_media",
        ["product_id", "media_asset_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_product_media_product_asset", "product_media", type_="unique")
    op.drop_index("ix_products_admin_page", table_name="products")
    op.drop_column("products", "archived_at")
