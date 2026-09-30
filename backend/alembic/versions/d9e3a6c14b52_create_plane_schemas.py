"""create control and tenant plane schemas (empty)

Physical plane separation starts as logical separation inside one cluster:
the existing `public` schema stays the Global Knowledge Plane and is not
touched, while two new empty schemas are created for the Control Plane and
the Tenant Data Plane (docs/architecture-v2.md §1.2).

No tables are created here. This migration only reserves the namespaces so
later phases have somewhere to put tenant and control tables.

Revision ID: d9e3a6c14b52
Revises: c8d2f5b03a41
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d9e3a6c14b52"
down_revision: Union[str, Sequence[str], None] = "c8d2f5b03a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("create schema if not exists control")
    op.execute("create schema if not exists tenant")


def downgrade() -> None:
    # RESTRICT is the PostgreSQL default and is deliberate here: if a later
    # phase has put tables in these schemas, this downgrade must FAIL loudly
    # rather than silently destroy tenant or control data. Dropping them is
    # only safe while they are empty, which is true in this phase.
    op.execute("drop schema if exists control restrict")
    op.execute("drop schema if exists tenant restrict")
