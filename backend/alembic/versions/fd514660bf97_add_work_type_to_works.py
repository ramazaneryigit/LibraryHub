"""add work type to works

Revision ID: fd514660bf97
Revises: ca8d6e5a605a
Create Date: 2026-09-21 10:16:32.913368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd514660bf97'
down_revision: Union[str, Sequence[str], None] = 'ca8d6e5a605a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    op.add_column(
        "works",
        sa.Column(
            "work_type",
            sa.String(length=100),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "works",
        "work_type",
    )