"""Add revocable access tokens to authentication sessions.

Revision ID: 20261022_0002
Revises: 20261022_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_0002"
down_revision: str | None = "20261022_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("access_token_hash", sa.LargeBinary(), nullable=True))
    op.add_column(
        "auth_sessions",
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_auth_sessions_access_token_hash",
        "auth_sessions",
        ["access_token_hash"],
    )
    op.execute(
        """
        UPDATE auth_sessions
        SET access_token_hash = decode(
                md5(id::text || 'access') || md5(id::text || 'token'),
                'hex'
            ),
            access_expires_at = created_at,
            revoked_at = COALESCE(revoked_at, now())
        WHERE access_token_hash IS NULL
        """
    )
    op.alter_column("auth_sessions", "access_token_hash", nullable=False)
    op.alter_column("auth_sessions", "access_expires_at", nullable=False)


def downgrade() -> None:
    op.drop_constraint(
        "uq_auth_sessions_access_token_hash",
        "auth_sessions",
        type_="unique",
    )
    op.drop_column("auth_sessions", "access_expires_at")
    op.drop_column("auth_sessions", "access_token_hash")
