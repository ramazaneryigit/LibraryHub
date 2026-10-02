"""the queue remembers which entity the incoming name created

Without this a merge decision has nothing to merge. The queue stores the name, a
new entity is created for it, and the two are never connected -- so "these are the
same person" would have to be re-resolved by name, which is the matching that
produced the suggestion in the first place.

The id cannot be written when the queue row is created, because the row is created
before the entity: `resolve_agent` records the resemblance and returns nothing, and
the caller creates the entity afterwards. So it is backfilled -- `agent_for` fills
in the open rows for that name as soon as it has an id.

Revision ID: b6d9f24c7e31
Revises: a3f7e1c85d29
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b6d9f24c7e31"
down_revision: Union[str, Sequence[str], None] = "a3f7e1c85d29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "alter table public.authority_candidates "
        "add column if not exists incoming_entity_id uuid "
        "references public.entities(id) on delete cascade"
    )

    op.execute(
        "create index if not exists ix_authority_candidates_incoming_entity "
        "on public.authority_candidates (incoming_entity_id)"
    )


def downgrade() -> None:
    op.execute("drop index if exists public.ix_authority_candidates_incoming_entity")
    op.execute(
        "alter table public.authority_candidates "
        "drop column if exists incoming_entity_id"
    )
