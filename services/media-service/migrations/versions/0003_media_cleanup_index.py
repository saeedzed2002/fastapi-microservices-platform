"""add abandoned upload cleanup index"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_media_cleanup_index"
down_revision: str | Sequence[str] | None = "0002_outbox_publish_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_media_assets_cleanup_candidates",
        "media_assets",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_cleanup_candidates", table_name="media_assets")
