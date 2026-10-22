"""Add append-only authentication security events.

Revision ID: 20261022_0005
Revises: 20261022_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261022_0005"
down_revision: str | None = "20261022_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("subject_hash", sa.LargeBinary(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_security_audit_events_occurred_at",
        "security_audit_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_security_audit_events_user_id_occurred_at",
        "security_audit_events",
        ["user_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("security_audit_events")
