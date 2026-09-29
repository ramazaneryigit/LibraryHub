"""optimize normalized work title trigram index

Revision ID: 9f25b0d7306d
Revises: 2b297de50358
Create Date: 2026-09-29
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9f25b0d7306d"
down_revision: Union[str, Sequence[str], None] = "2b297de50358"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_works_canonical_title_trgm
        """
    )

    op.execute(
        """
        CREATE INDEX ix_works_canonical_title_lower_trgm
        ON works
        USING gin (lower(canonical_title) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_works_canonical_title_lower_trgm
        """
    )

    op.execute(
        """
        CREATE INDEX ix_works_canonical_title_trgm
        ON works
        USING gin (canonical_title gin_trgm_ops)
        """
    )