"""add classification model

Revision ID: 4677ebcd79c0
Revises: fd514660bf97
Create Date: 2026-09-21 12:10:12.434092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4677ebcd79c0'
down_revision: Union[str, Sequence[str], None] = 'fd514660bf97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Allow CLASSIFICATION as an Entity subtype.
    op.drop_constraint(
        "ck_entities_entity_type",
        "entities",
        type_="check",
    )

    op.create_check_constraint(
        "ck_entities_entity_type",
        "entities",
        "entity_type IN ("
        "'PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', "
        "'EXPRESSION', 'MANIFESTATION', 'ITEM', 'PLACE', "
        "'TIME_SPAN', 'CLASSIFICATION'"
        ")",
    )

    op.create_table(
        'vocabulary_schemes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('scheme_type', sa.String(length=100), nullable=False),
        sa.Column('version', sa.String(length=100), nullable=True),
        sa.Column('uri', sa.String(length=1000), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(
        op.f('ix_vocabulary_schemes_code'),
        'vocabulary_schemes',
        ['code'],
        unique=True
    )

    op.create_table(
        'classification_nodes',
        sa.Column('entity_id', sa.Uuid(), nullable=False),
        sa.Column('scheme_id', sa.Uuid(), nullable=False),
        sa.Column('notation', sa.String(length=200), nullable=False),
        sa.Column('caption', sa.String(length=1000), nullable=True),
        sa.Column('parent_entity_id', sa.Uuid(), nullable=True),
        sa.Column('uri', sa.String(length=1000), nullable=True),
        sa.Column('status', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ['entity_id'],
            ['entities.id'],
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['parent_entity_id'],
            ['classification_nodes.entity_id'],
            ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['scheme_id'],
            ['vocabulary_schemes.id'],
            ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('entity_id'),
        sa.UniqueConstraint(
            'scheme_id',
            'notation',
            name='uq_classification_scheme_notation'
        )
    )

    op.create_index(
        op.f('ix_classification_nodes_parent_entity_id'),
        'classification_nodes',
        ['parent_entity_id'],
        unique=False
    )

    op.create_index(
        op.f('ix_classification_nodes_scheme_id'),
        'classification_nodes',
        ['scheme_id'],
        unique=False
    )

    # ClassificationNode must belong to a CLASSIFICATION Entity.
    op.execute("""
        CREATE TRIGGER trg_classification_nodes_validate_entity_type
        BEFORE INSERT OR UPDATE OF entity_id
        ON classification_nodes
        FOR EACH ROW
        EXECUTE FUNCTION validate_entity_subtype_type('CLASSIFICATION')
    """)

    op.create_table(
        'work_classifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('work_entity_id', sa.Uuid(), nullable=False),
        sa.Column('classification_entity_id', sa.Uuid(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('assigned_by', sa.String(length=200), nullable=True),
        sa.Column('source', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ['classification_entity_id'],
            ['classification_nodes.entity_id'],
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['work_entity_id'],
            ['works.entity_id'],
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'work_entity_id',
            'classification_entity_id',
            name='uq_work_classification'
        )
    )

    op.create_index(
        op.f('ix_work_classifications_classification_entity_id'),
        'work_classifications',
        ['classification_entity_id'],
        unique=False
    )

    op.create_index(
        op.f('ix_work_classifications_work_entity_id'),
        'work_classifications',
        ['work_entity_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f('ix_work_classifications_work_entity_id'),
        table_name='work_classifications'
    )
    op.drop_index(
        op.f('ix_work_classifications_classification_entity_id'),
        table_name='work_classifications'
    )
    op.drop_table('work_classifications')

    op.execute("""
        DROP TRIGGER IF EXISTS
        trg_classification_nodes_validate_entity_type
        ON classification_nodes
    """)

    op.drop_index(
        op.f('ix_classification_nodes_scheme_id'),
        table_name='classification_nodes'
    )
    op.drop_index(
        op.f('ix_classification_nodes_parent_entity_id'),
        table_name='classification_nodes'
    )
    op.drop_table('classification_nodes')

    op.drop_index(
        op.f('ix_vocabulary_schemes_code'),
        table_name='vocabulary_schemes'
    )
    op.drop_table('vocabulary_schemes')

    # Restore the previous Entity type constraint.
    op.drop_constraint(
        "ck_entities_entity_type",
        "entities",
        type_="check",
    )

    op.create_check_constraint(
        "ck_entities_entity_type",
        "entities",
        "entity_type IN ("
        "'PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', "
        "'EXPRESSION', 'MANIFESTATION', 'ITEM', 'PLACE', "
        "'TIME_SPAN'"
        ")",
    )
