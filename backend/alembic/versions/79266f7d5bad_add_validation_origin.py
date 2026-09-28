"""add validation origin

Revision ID: 79266f7d5bad
Revises: de3f4dacacac
Create Date: 2026-09-28 08:15:48.095302

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "79266f7d5bad"
down_revision: Union[str, Sequence[str], None] = "de3f4dacacac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the column temporarily as nullable.
    op.add_column(
        "classification_validations",
        sa.Column(
            "origin",
            sa.String(length=20),
            nullable=True,
        ),
    )

    # 2. Existing records were created before origin existed.
    # Start by marking them automatic.
    op.execute(
        """
        UPDATE classification_validations
        SET origin = 'automatic'
        """
    )

    # 3. These two known records were manually created.
    op.execute(
        """
        UPDATE classification_validations
        SET origin = 'manual'
        WHERE id IN (
            '668c98b2-da5f-4088-aff5-beb49b6f550d',
            'f4ee1430-9870-44d3-bda0-2cafc02a85af'
        )
        """
    )

    # 4. After backfilling all existing rows, make the column NOT NULL.
    op.alter_column(
        "classification_validations",
        "origin",
        existing_type=sa.String(length=20),
        nullable=False,
    )

    # 5. Database-level protection.
    op.create_check_constraint(
        "ck_classification_validation_origin",
        "classification_validations",
        "origin IN ('manual', 'automatic')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_classification_validation_origin",
        "classification_validations",
        type_="check",
    )

    op.drop_column(
        "classification_validations",
        "origin",
    )