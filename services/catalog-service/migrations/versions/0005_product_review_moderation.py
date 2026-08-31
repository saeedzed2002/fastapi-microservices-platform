"""add moderated product reviews with one reply level"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_product_review_moderation"
down_revision: str | Sequence[str] | None = "0004_product_page_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("author_role", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("moderated_by", sa.Uuid(), nullable=True),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_product_reviews_status",
        ),
        sa.CheckConstraint(
            "author_role IN ('customer', 'admin')",
            name="ck_product_reviews_author_role",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["product_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_reviews_author_id", "product_reviews", ["author_id"])
    op.create_index(
        "ix_product_reviews_public_page",
        "product_reviews",
        ["product_id", "status", "parent_id", "created_at", "id"],
    )
    op.create_index(
        "ix_product_reviews_author_page",
        "product_reviews",
        ["author_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_reviews_author_page", table_name="product_reviews")
    op.drop_index("ix_product_reviews_public_page", table_name="product_reviews")
    op.drop_index("ix_product_reviews_author_id", table_name="product_reviews")
    op.drop_table("product_reviews")
