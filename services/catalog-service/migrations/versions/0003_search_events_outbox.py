"""publish Catalog product events for Search"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_search_events_outbox"
down_revision: str | Sequence[str] | None = "0002_category_management_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_claim_token", sa.Uuid(), nullable=True),
        sa.Column("publish_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])
    op.create_index("ix_outbox_messages_published_at", "outbox_messages", ["published_at"])
    op.execute(
        """
        INSERT INTO outbox_messages (
            id, event_id, event_type, aggregate_type, aggregate_id, payload,
            correlation_id, causation_id, trace_id, occurred_at, published_at,
            publish_claim_token, publish_claimed_at, attempts, last_error
        )
        SELECT
            md5(products.id::text || clock_timestamp()::text || random()::text)::uuid,
            md5(products.id::text || clock_timestamp()::text || random()::text)::uuid,
            'product.created.v1',
            'product',
            products.id,
            json_build_object(
                'product_id', products.id::text,
                'slug', products.slug,
                'name', products.name,
                'description', products.description,
                'status', products.status,
                'brand_id',
                    CASE WHEN products.brand_id IS NULL THEN NULL ELSE products.brand_id::text END,
                'category_id',
                    CASE WHEN products.category_id IS NULL THEN NULL
                    ELSE products.category_id::text END,
                'price_amount', products.price_amount::text,
                'currency', products.currency,
                'attributes', products.attributes,
                'published_at',
                    CASE WHEN products.published_at IS NULL THEN NULL
                    ELSE to_char(
                        products.published_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ) END,
                'updated_at', to_char(
                    products.updated_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                )
            ),
            products.id,
            NULL,
            repeat('0', 32),
            now(),
            NULL,
            NULL,
            NULL,
            0,
            NULL
        FROM products
        """
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_published_at", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
