"""suppress the migration bucket, and let the projections respect suppression

The defect
---------
Six holdings resolved no institution and appeared in the union catalogue as
"Kurum kaydedilmemiş". The chain `holding -> branch -> organization ->
collective_agent_entity_id` breaks at the last step: `Unassigned items
(migration)` is a bucket the legacy item migration created, and its organization
row has a null `collective_agent_entity_id` because it is not an institution.

So the honest reading is not "a library whose name is missing". It is *not a
library*, and a catalogue of a thousand libraries cannot list it beside them.

Why `status` and not a special case
-----------------------------------
`tenant.holdings.status` is already `('active', 'closed', 'suppressed')`. A
suppressed holding is one an institution has decided not to publish; excluded
from the union catalogue is what that word means. Using it, rather than teaching
each projection to recognise this particular tenant, is the difference between a
rule and a name.

Suppressing loses nothing, which was checked before it was done: those six
holdings carry **zero** items between them.

What is data and what is schema
-------------------------------
The suppression is data, and it is written as a condition rather than a list of
ids: every holding whose tenant's organization has no collective agent. That is
deterministic -- any database that ran the same legacy migration is in the same
state -- so it is not a patch to this environment.

The two projections change shape, so they are recreated here rather than patched.

Revision ID: e2a7c3d58b61
Revises: d1f6b2c47a59
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2a7c3d58b61"
down_revision: Union[str, Sequence[str], None] = "d1f6b2c47a59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPRESS = """
update tenant.holdings h
   set status = 'suppressed', updated_at = now()
 where h.status <> 'suppressed'
   and h.tenant_id in (
        select o.tenant_id
          from control.organizations o
         where o.collective_agent_entity_id is null
   )
"""


HOLDINGS_COMPAT = """
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
where th.status <> 'suppressed'
"""


ITEMS_COMPAT = """
create or replace view public.items_compat as
select
    coalesce(ti.legacy_entity_id, ti.id) as entity_id,
    ti.barcode,
    ti.shelfmark,
    ti.condition,
    ti.availability_status,
    ti.notes,
    th.manifestation_entity_id,
    co.collective_agent_entity_id        as holding_institution_entity_id
from tenant.items ti
join tenant.holdings th
  on th.id = ti.holding_id
left join control.branches b
       on b.id = th.branch_id
left join control.organizations co
       on co.id = b.organization_id
where th.status <> 'suppressed'
"""


# The views as they were before this revision: identical, without the filter.
HOLDINGS_COMPAT_BEFORE = HOLDINGS_COMPAT.replace(
    "where th.status <> 'suppressed'\n", ""
)

ITEMS_COMPAT_BEFORE = ITEMS_COMPAT.replace(
    "where th.status <> 'suppressed'\n", ""
)


def upgrade() -> None:
    op.execute(SUPPRESS)
    op.execute(HOLDINGS_COMPAT)
    op.execute(ITEMS_COMPAT)


def downgrade() -> None:
    op.execute(HOLDINGS_COMPAT_BEFORE)
    op.execute(ITEMS_COMPAT_BEFORE)

    # Only the ones this revision suppressed, and only the ones that came from a
    # tenant with no collective agent -- an institution that suppressed one of
    # its own holdings deliberately keeps that decision.
    op.execute(
        """
        update tenant.holdings h
           set status = 'active', updated_at = now()
         where h.status = 'suppressed'
           and h.tenant_id in (
                select o.tenant_id
                  from control.organizations o
                 where o.collective_agent_entity_id is null
           )
        """
    )
