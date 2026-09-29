"""add trigram work title search

Revision ID: 2b297de50358
Revises: c91f4a20de76
Create Date: 2026-09-29
"""

from typing import Sequence, Union

from alembic import op


revision: str = "2b297de50358"
down_revision: Union[str, Sequence[str], None] = "c91f4a20de76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_works_canonical_title_trgm
        ON works
        USING gin (canonical_title gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_works_canonical_title_trgm
        """
    )