"""add entity type check constraint

Revision ID: 83c5b28687f9
Revises: 7f298d228e4d
Create Date: 2026-09-15 08:47:38.399605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83c5b28687f9'
down_revision: Union[str, Sequence[str], None] = '7f298d228e4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_entities_entity_type",
        "entities",
        "entity_type IN ('PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', 'EXPRESSION', 'MANIFESTATION', 'ITEM', 'PLACE', 'TIME_SPAN')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_entities_entity_type",
        "entities",
        type_="check",
    )