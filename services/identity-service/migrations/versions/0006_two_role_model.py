"""retire legacy staff roles in favor of admin and customer"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_two_role_model"
down_revision: str | Sequence[str] | None = "0005_staff_authentication_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve active administrator and customer identities. The retired
    # support-only account is promoted to the sole privileged role because the
    # initial platform intentionally has no separate support role. Unknown
    # legacy role sets are suspended rather than granted elevated access.
    op.execute(
        """
        UPDATE users
        SET
            status = CASE
                WHEN (roles::jsonb ? 'admin')
                     OR (roles::jsonb ? 'support_agent')
                     OR (roles::jsonb ? 'customer') THEN status
                ELSE 'suspended'
            END,
            roles = CASE
                WHEN (roles::jsonb ? 'admin') OR (roles::jsonb ? 'support_agent')
                    THEN '["admin"]'::json
                WHEN roles::jsonb ? 'customer' THEN '["customer"]'::json
                ELSE '[]'::json
            END
        """
    )
    op.execute(
        """
        UPDATE refresh_sessions
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE revoked_at IS NULL
          AND user_id IN (
              SELECT id
              FROM users
              WHERE status = 'suspended' AND roles::jsonb = '[]'::jsonb
          )
        """
    )


def downgrade() -> None:
    # Removed role assignments cannot be reconstructed safely.
    pass
