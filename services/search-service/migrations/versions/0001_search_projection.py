"""create the rebuildable Catalog search projection"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_search_projection"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_documents",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=260), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(slug, '') "
                "|| ' ' || coalesce(description, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("product_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_search_documents_brand_id", "search_documents", ["brand_id"])
    op.create_index("ix_search_documents_category_id", "search_documents", ["category_id"])
    op.create_index("ix_search_documents_currency", "search_documents", ["currency"])
    op.create_index("ix_search_documents_status", "search_documents", ["status"])
    op.create_index(
        "ix_search_documents_search_vector",
        "search_documents",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_table(
        "search_tombstones",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_inbox_messages_event_type", "inbox_messages", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_inbox_messages_event_type", table_name="inbox_messages")
    op.drop_table("inbox_messages")
    op.drop_table("search_tombstones")
    op.drop_index("ix_search_documents_search_vector", table_name="search_documents")
    op.drop_index("ix_search_documents_status", table_name="search_documents")
    op.drop_index("ix_search_documents_currency", table_name="search_documents")
    op.drop_index("ix_search_documents_category_id", table_name="search_documents")
    op.drop_index("ix_search_documents_brand_id", table_name="search_documents")
    op.drop_table("search_documents")
