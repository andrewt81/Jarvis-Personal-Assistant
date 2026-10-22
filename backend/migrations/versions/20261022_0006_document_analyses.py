"""Add versioned document analyses.

Revision ID: 20261022_0006
Revises: 20261022_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261022_0006"
down_revision: str | None = "20261022_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("document_type", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=False),
        sa.Column("deadlines", postgresql.JSONB(), nullable=False),
        sa.Column("suggested_actions", postgresql.JSONB(), nullable=False),
        sa.Column("missing_information", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_document_analyses_household_document_created",
        "document_analyses",
        ["household_id", "document_id", "created_at"],
    )
    op.create_unique_constraint(
        "uq_document_analyses_document_source",
        "document_analyses",
        ["document_id", "source_sha256"],
    )


def downgrade() -> None:
    op.drop_table("document_analyses")
