"""add ingestion batches

Revision ID: 49f61999a6f3
Revises: 9f25b0d7306d
Create Date: 2026-09-29 14:04:08.132342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49f61999a6f3'
down_revision: Union[str, Sequence[str], None] = '9f25b0d7306d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ingestion_batches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_system', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('created', sa.Integer(), nullable=False),
        sa.Column('updated', sa.Integer(), nullable=False),
        sa.Column('unchanged', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        op.f('ix_ingestion_batches_source_system'),
        'ingestion_batches',
        ['source_system'],
        unique=False,
    )

    op.create_index(
        op.f('ix_ingestion_batches_status'),
        'ingestion_batches',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_ingestion_batches_status'),
        table_name='ingestion_batches',
    )

    op.drop_index(
        op.f('ix_ingestion_batches_source_system'),
        table_name='ingestion_batches',
    )

    op.drop_table('ingestion_batches')
