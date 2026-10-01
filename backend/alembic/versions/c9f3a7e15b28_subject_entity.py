"""bind an account to the authority record it acts for

A publisher account has to know which publisher it *is*, or "my titles" is
unanswerable. An academician account has the same problem for the same reason: it
acts for one `persons` entity.

So the column is general rather than publisher-specific -- `subject_entity_id`, the
record this account speaks for. A library's staff act for a tenant and leave it
null. It is nullable because most accounts do not need it, and a value that has to
be invented for every account would be a value nobody trusts.

No foreign key to `entities` in both directions, only one: the account points at
the record. Deleting an authority record does not delete the account, which is the
right way round -- an account is identity, an authority record is content.

Revision ID: c9f3a7e15b28
Revises: b7e1c4a92d63
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c9f3a7e15b28"
down_revision: Union[str, Sequence[str], None] = "b7e1c4a92d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "alter table control.users "
        "add column if not exists subject_entity_id uuid "
        "references public.entities(id) on delete set null"
    )

    op.execute(
        "create index if not exists ix_users_subject_entity "
        "on control.users (subject_entity_id)"
    )


def downgrade() -> None:
    op.execute("drop index if exists control.ix_users_subject_entity")
    op.execute(
        "alter table control.users drop column if exists subject_entity_id"
    )
