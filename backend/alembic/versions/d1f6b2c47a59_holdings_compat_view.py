"""project holdings, so a library does not need a copy to be visible

The defect this fixes
---------------------
"Which library has this?" was answered by walking `public.items_compat` -- an
*item* projection -- and reading the institution off each item. So a library that
had catalogued the holding but not the individual copies was invisible. Measured
on this database: `Bilgi Yönetimine Giriş` has two holdings, and one of them, a
library with the book on the shelf and no copy records, did not appear at all.

That is not an edge case. It is the normal state of a serial, of a collection,
of a donation not yet itemised, and of a migration that moved holdings before
items -- which is exactly what `migrated-*` rows are.

Why a view rather than a query change
-------------------------------------
The institution is a property of the *holding*: `holdings.branch_id` ->
`branches.organization_id` -> `organizations.collective_agent_entity_id`. That
chain has nothing to do with items, and reaching it through items was the whole
mistake. Expressing the same chain once, as a view, means every reader asks the
same question the same way -- and a union catalogue of a thousand libraries is
not a place to have two answers to "who holds this".

`items_compat` stays. It is the item-level projection and per-copy availability
still comes from it; this is the level above, and the two are complements.

Revision ID: d1f6b2c47a59
Revises: c9e5a1b36f48
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d1f6b2c47a59"
down_revision: Union[str, Sequence[str], None] = "c9e5a1b36f48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEW = """
create or replace view public.holdings_compat as
select
    th.id                          as holding_id,
    th.tenant_id,
    th.manifestation_entity_id,
    th.expression_entity_id,
    th.local_holding_key,
    th.holding_type,
    th.call_number,
    th.status,
    co.collective_agent_entity_id  as holding_institution_entity_id,
    coalesce(i.item_count, 0)      as item_count,
    coalesce(i.availability, '{}'::jsonb) as availability
from tenant.holdings th
left join control.branches b
       on b.id = th.branch_id
left join control.organizations co
       on co.id = b.organization_id
left join lateral (
    select
        coalesce(sum(grouped.n), 0) as item_count,
        coalesce(
            jsonb_object_agg(grouped.status, grouped.n),
            '{}'::jsonb
        ) as availability
    from (
        select
            coalesce(availability_status, 'unknown') as status,
            count(*) as n
        from tenant.items
        where holding_id = th.id
        group by 1
    ) grouped
) i on true
"""


def upgrade() -> None:
    op.execute(VIEW)


def downgrade() -> None:
    op.execute("drop view if exists public.holdings_compat")
