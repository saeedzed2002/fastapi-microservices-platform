"""allow phone-only customer identity projections"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phone_identity_projection"
down_revision: str | Sequence[str] | None = "0002_identity_event_inbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("customers", "email", existing_type=sa.String(length=320), nullable=True)


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE customers SET email = 'unknown@identity.invalid' WHERE email IS NULL")
    )
    op.alter_column("customers", "email", existing_type=sa.String(length=320), nullable=False)
