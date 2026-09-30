"""migrate legacy items into the Tenant Data Plane

Architecture v2 §16 Aşama 4. `public.items` rows are copied into
`tenant.holdings` + `tenant.items`, and a compatibility view reproduces the old
shape so the existing API contract keeps working off the new tables.

Nothing is deleted. `public.items`, `public.manifestation_item` and
`public.item_agent_relation` stay exactly as they are and stay writable, which
is what makes the downgrade a single step. Dropping them is Aşama 6.

Where an item's institution comes from
--------------------------------------
`item_agent_relation` with `role = 'holding_institution'`, mapped through
`control.organizations.collective_agent_entity_id`, then to that organization's
default branch. The role filter is deliberate: it is the application's own
existing rule (it is what `services/work_detail.py` has always filtered on), so
the migrated attribution matches what the API reported before.

Items whose custody is recorded under a *different* role, or not recorded at
all, are **not guessed**. They go to a dedicated, clearly labelled fallback
tenant so a human can attribute them. Silently assigning them to whichever
library happens to be nearby would be worse than leaving them visibly
unassigned.

The fallback organization deliberately has `collective_agent_entity_id = NULL`,
which means the compatibility view reports no holding institution for those
items -- exactly what the API reported before the migration, so the contract
does not shift.

Generated keys
--------------
Every migrated Holding needs a `local_holding_key`, and two of the legacy items
have neither a barcode nor a shelfmark to derive one from. Rather than invent
something per item, the key is derived from the group itself:
`migrated-<manifestation uuid>`. One Holding is created per distinct
(tenant, branch, manifestation), which is the natural grouping -- copies of the
same manifestation on the same shelf share a call number.

What this migration refuses to do
---------------------------------
It asserts that every `public.items` row produced exactly one `tenant.items`
row, and raises if not. A migration that silently drops a row is worse than one
that stops.

Revision ID: c5d8f1b69a07
Revises: b4c7e0a58f96
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d8f1b69a07"
down_revision: Union[str, Sequence[str], None] = "b4c7e0a58f96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FALLBACK_TENANT_SLUG = "unassigned"


# Per-item mapping: which tenant, branch and manifestation does this legacy item
# belong to? Used twice below (holdings, then items), so it lives in one place.
ITEM_TARGET_CTE = """
    select
        i.entity_id as item_entity_id,
        mi.manifestation_entity_id,
        case when org.id is not null then org.tenant_id else fb.tenant_id end as tenant_id,
        case when org.id is not null then br.id else fb.branch_id end as branch_id
    from public.items i
    join public.manifestation_item mi
      on mi.item_entity_id = i.entity_id
    left join lateral (
        select o.id, o.tenant_id
        from public.item_agent_relation iar
        join control.organizations o
          on o.collective_agent_entity_id = iar.agent_entity_id
        where iar.item_entity_id = i.entity_id
          and iar.role = 'holding_institution'
        limit 1
    ) org on true
    left join lateral (
        select b.id
        from control.branches b
        where b.organization_id = org.id
        order by b.is_default desc, b.code
        limit 1
    ) br on true
    left join lateral (
        select t.id as tenant_id, b.id as branch_id
        from control.tenants t
        join control.organizations o on o.tenant_id = t.id
        join control.branches b on b.organization_id = o.id
        where t.slug = '{slug}'
        order by b.is_default desc, b.code
        limit 1
    ) fb on true
""".format(slug=FALLBACK_TENANT_SLUG)


# Created only when at least one item would otherwise have no home.
FALLBACK_TENANT_SQL = f"""
do $$
declare
    v_needed   boolean;
    v_tenant   uuid;
    v_org      uuid;
begin
    select exists (
        select 1
        from public.items i
        where not exists (
            select 1
            from public.item_agent_relation iar
            join control.organizations o
              on o.collective_agent_entity_id = iar.agent_entity_id
            where iar.item_entity_id = i.entity_id
              and iar.role = 'holding_institution'
        )
    ) into v_needed;

    if not v_needed then
        return;
    end if;

    select id into v_tenant from control.tenants where slug = '{FALLBACK_TENANT_SLUG}';

    if v_tenant is not null then
        return;
    end if;

    insert into control.tenants
        (id, slug, display_name, status, cluster_id, created_at, updated_at)
    values
        (gen_random_uuid(), '{FALLBACK_TENANT_SLUG}',
         'Unassigned items (migration)', 'active', 'primary', now(), now())
    returning id into v_tenant;

    -- No collective_agent_entity_id on purpose: this is not an authority
    -- record, and leaving it NULL makes the compatibility view report no
    -- holding institution for these items, matching the pre-migration API.
    insert into control.organizations
        (id, tenant_id, collective_agent_entity_id, name, org_type, created_at)
    values
        (gen_random_uuid(), v_tenant, null,
         'Unassigned items (migration)', 'migration', now())
    returning id into v_org;

    insert into control.branches
        (id, tenant_id, organization_id, code, name, is_default, created_at)
    values
        (gen_random_uuid(), v_tenant, v_org, 'MAIN', 'Main', true, now());

    insert into control.tenant_databases
        (tenant_id, cluster_id, dsn_secret_ref, updated_at)
    values
        (v_tenant, 'primary', 'env:DATABASE_URL', now());
end
$$;
"""


HOLDINGS_SQL = f"""
with item_target as (
{ITEM_TARGET_CTE}
)
insert into tenant.holdings
    (id, tenant_id, branch_id, manifestation_entity_id, holding_type,
     local_holding_key, status, created_at, updated_at)
select
    gen_random_uuid(),
    d.tenant_id,
    d.branch_id,
    d.manifestation_entity_id,
    'physical',
    'migrated-' || replace(d.manifestation_entity_id::text, '-', ''),
    'active',
    now(),
    now()
from (
    select distinct tenant_id, branch_id, manifestation_entity_id
    from item_target
    where tenant_id is not null and branch_id is not null
) d;
"""


ITEMS_SQL = f"""
with item_target as (
{ITEM_TARGET_CTE}
)
insert into tenant.items
    (id, tenant_id, holding_id, legacy_entity_id, barcode, shelfmark,
     condition, availability_status, notes, lifecycle_status,
     created_at, updated_at)
select
    gen_random_uuid(),
    t.tenant_id,
    h.id,
    t.item_entity_id,
    i.barcode,
    i.shelfmark,
    i.condition,
    coalesce(i.availability_status, 'unknown'),
    i.notes,
    'active',
    now(),
    now()
from item_target t
join public.items i on i.entity_id = t.item_entity_id
join tenant.holdings h
  on h.tenant_id = t.tenant_id
 and h.branch_id = t.branch_id
 and h.manifestation_entity_id = t.manifestation_entity_id
where t.tenant_id is not null and t.branch_id is not null;
"""


# Fail loudly rather than dropping rows on the floor.
VERIFY_SQL = """
do $$
declare
    v_legacy  bigint;
    v_migrated bigint;
begin
    select count(*) into v_legacy from public.items;
    select count(*) into v_migrated from tenant.items;

    if v_legacy <> v_migrated then
        raise exception
            'Item migration is incomplete: % legacy rows but % migrated rows',
            v_legacy, v_migrated;
    end if;
end
$$;
"""


# Read-only bridge that lets the existing API keep its exact shape while the
# rows live in two places. Once Aşama 5 moves the write path the second branch
# becomes empty and can be dropped.
ITEMS_COMPAT_VIEW_SQL = """
create view public.items_compat as
select
    coalesce(ti.legacy_entity_id, ti.id) as entity_id,
    ti.barcode,
    ti.shelfmark,
    ti.condition,
    ti.availability_status,
    ti.notes,
    th.manifestation_entity_id,
    co.collective_agent_entity_id as holding_institution_entity_id
from tenant.items ti
join tenant.holdings th on th.id = ti.holding_id
join control.organizations co on co.tenant_id = ti.tenant_id

union all

-- Items created through the API after the migration still land in the legacy
-- global tables (the write path moves in Aşama 5), so they have to stay
-- visible here or the contract would silently lose them.
select
    li.entity_id,
    li.barcode,
    li.shelfmark,
    li.condition,
    li.availability_status,
    li.notes,
    mi.manifestation_entity_id,
    (
        select iar.agent_entity_id
        from public.item_agent_relation iar
        where iar.item_entity_id = li.entity_id
          and iar.role = 'holding_institution'
        limit 1
    ) as holding_institution_entity_id
from public.items li
join public.manifestation_item mi on mi.item_entity_id = li.entity_id
where not exists (
    select 1
    from tenant.items ti2
    where ti2.legacy_entity_id = li.entity_id
);
"""


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("legacy_entity_id", sa.Uuid(), nullable=True),
        schema="tenant",
    )
    op.create_unique_constraint(
        "uq_items_legacy_entity_id",
        "items",
        ["legacy_entity_id"],
        schema="tenant",
    )

    op.execute(FALLBACK_TENANT_SQL)
    op.execute(HOLDINGS_SQL)
    op.execute(ITEMS_SQL)
    op.execute(VERIFY_SQL)
    op.execute(ITEMS_COMPAT_VIEW_SQL)


def downgrade() -> None:
    op.execute("drop view if exists public.items_compat")

    # Everything currently in these tables came from this migration, so
    # clearing them restores the pre-migration state. `public.items` was never
    # touched and is the source of truth throughout.
    op.execute("delete from tenant.items")
    op.execute("delete from tenant.holdings")

    op.execute(
        f"""
        delete from control.tenant_databases
        where tenant_id in (select id from control.tenants where slug = '{FALLBACK_TENANT_SLUG}')
        """
    )
    op.execute(
        f"""
        delete from control.branches
        where tenant_id in (select id from control.tenants where slug = '{FALLBACK_TENANT_SLUG}')
        """
    )
    op.execute(
        f"""
        delete from control.organizations
        where tenant_id in (select id from control.tenants where slug = '{FALLBACK_TENANT_SLUG}')
        """
    )
    op.execute(
        f"delete from control.tenants where slug = '{FALLBACK_TENANT_SLUG}'"
    )

    op.drop_constraint(
        "uq_items_legacy_entity_id",
        "items",
        type_="unique",
        schema="tenant",
    )
    op.drop_column("items", "legacy_entity_id", schema="tenant")
