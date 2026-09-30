"""add source_systems registry and link source_records to it

Purely additive provenance groundwork. The registry is created empty and
source_records.source_system_id is nullable, so not a single existing row
changes value and the legacy `source_system` string column keeps working.
Backfilling the registry from existing distinct source systems, and populating
source_system_id, is deliberately left to a later phase
(docs/architecture-v2.md §6 and §16, Aşama 2).

Revision ID: c8d2f5b03a41
Revises: b7c1e4a92f30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d2f5b03a41"
down_revision: Union[str, Sequence[str], None] = "b7c1e4a92f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("system_type", sa.String(length=100), nullable=False),
        sa.Column("trust_level", sa.Integer(), nullable=False),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_source_systems_code",
        "source_systems",
        ["code"],
        unique=True,
    )

    op.add_column(
        "source_records",
        sa.Column("source_system_id", sa.Uuid(), nullable=True),
    )

    op.create_index(
        "ix_source_records_source_system_id",
        "source_records",
        ["source_system_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_source_records_source_system",
        "source_records",
        "source_systems",
        ["source_system_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_source_records_source_system",
        "source_records",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_source_records_source_system_id",
        table_name="source_records",
    )

    op.drop_column("source_records", "source_system_id")

    op.drop_index(
        "ix_source_systems_code",
        table_name="source_systems",
    )

    op.drop_table("source_systems")
