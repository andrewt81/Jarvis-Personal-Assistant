"""Link immutable document revisions without replacing existing originals.

Revision ID: 20261125_0007
Revises: 20261022_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261125_0007"
down_revision: str | None = "20261022_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_unique_constraint("uq_documents_id_household", "documents", ["id", "household_id"])
    op.create_table(
        "document_revisions",
        sa.Column("previous_document_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["previous_document_id", "household_id"],
            ["documents.id", "documents.household_id"],
            ondelete="RESTRICT",
            name="fk_revision_previous_household",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "household_id"],
            ["documents.id", "documents.household_id"],
            ondelete="RESTRICT",
            name="fk_revision_document_household",
        ),
        sa.CheckConstraint("previous_document_id <> document_id", name="ck_revision_distinct_ids"),
    )
    op.create_index("ix_document_revisions_household", "document_revisions", ["household_id"])


def downgrade() -> None:
    # Removing lineage from a populated archive would hide revision relationships.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM document_revisions)")).scalar():
        raise RuntimeError("Cannot remove revision schema while revision links exist")
    op.drop_table("document_revisions")
    op.drop_constraint("uq_documents_id_household", "documents", type_="unique")
