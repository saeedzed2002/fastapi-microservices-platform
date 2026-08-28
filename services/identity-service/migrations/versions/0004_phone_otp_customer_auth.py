"""add phone-based customer authentication"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phone_otp_customer_auth"
down_revision: str | Sequence[str] | None = "0003_outbox_publish_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=16), nullable=True))
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone")
