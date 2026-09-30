"""let a platform administrator exist without a tenant

Why
---
The global write endpoints now require `role = 'admin'`, but an admin was still
required to belong to a tenant -- so the platform's curator had to be invented as
a member of somebody's library. Reviewing the proposals tenants raise, merging two
identities, loading a batch: none of that belongs to an institution, and binding
it to one made the shared plane look like that institution's property.

`tenant_id` becomes nullable for exactly that case, and a check keeps it honest:
a tenant-less account must be an `admin`, because a librarian with no library
cannot act at all. The other direction stays open -- an institution's own
administrator may also curate the shared record.

What this does not do
---------------------
It does not weaken tenant isolation. `tenant.*` is still reached only through a
session scoped by `libraryhub.tenant_id`, and a user who has no tenant has
nothing to bind, so `tenant_db` refuses them rather than falling back to a
default. A platform administrator's reach is the global plane, and only the
global plane.

Revision ID: e4f1a7c25b83
Revises: d2e5f04bc159
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e4f1a7c25b83"
down_revision: Union[str, Sequence[str], None] = "d2e5f04bc159"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "control"
CONSTRAINT = "ck_users_tenant_required"


def upgrade() -> None:
    op.alter_column(
        "users",
        "tenant_id",
        schema=SCHEMA,
        existing_type=sa.Uuid(),
        nullable=True,
    )

    op.create_check_constraint(
        CONSTRAINT,
        "users",
        "tenant_id IS NOT NULL OR role = 'admin'",
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Making the column required again would fail on any platform administrator,
    # and a bare NOT NULL error names the column but not the accounts. Say which
    # ones are in the way.
    connection = op.get_bind()

    orphans = connection.execute(
        sa.text(
            f"select count(*) from {SCHEMA}.users where tenant_id is null"
        )
    ).scalar_one()

    if orphans:
        raise RuntimeError(
            f"{orphans} platform administrator(s) have no tenant. "
            "Give them one, or delete them, before downgrading: "
            f"select id, email from {SCHEMA}.users where tenant_id is null"
        )

    op.drop_constraint(CONSTRAINT, "users", schema=SCHEMA, type_="check")

    op.alter_column(
        "users",
        "tenant_id",
        schema=SCHEMA,
        existing_type=sa.Uuid(),
        nullable=False,
    )
