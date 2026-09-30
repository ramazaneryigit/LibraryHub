"""retire the legacy global item tables

What this completes
-------------------
Aşama 4 moved copies out of the global identity registry and into the tenant
plane, behind a compatibility view. Everything since has been removing the
reasons the legacy shape had to stay: the write path, the read paths, the
fixtures that referenced an ITEM entity, and the ownership relation that turned
out to be derivable from the structure.

The measurement before this migration, from `run_scale_checks.py`, was zero on
every count: every `public.items` row had a `tenant.items` counterpart, every
`manifestation_item` link was represented by the holding the copy sits under,
every `item_agent_relation` row agreed with the organization derived from
item -> holding -> branch -> organization, and no surviving record named an
entity of type ITEM.

The one thing that was NOT accounted for
----------------------------------------
Three rows in `identifiers` pointed at ITEM entities, and two of them were the
only identifier their copy had -- both on barcodeless copies at the Russian State
Library. Deleting the entities would have cascaded them away. So the identifiers
move to `tenant.item_identifiers` first: a copy's identifiers are the tenant's
data, exactly like its barcode, and the legacy model had nowhere else to put
them. `public.item_identifiers` exposes them globally the same way
`items_compat` exposes the copies.

The view becomes a projection rather than a compatibility shim
--------------------------------------------------------------
`items_compat` existed to present the tenant plane in the old shape while both
existed. With the legacy branch removed it is simply the global read of the
tenant plane, and that is load-bearing: a view runs with its owner's privileges
by default, so it sees every tenant's copies while a tenant-scoped session sees
only its own. That is the whole reason a global endpoint can answer "who holds
this" at all.

Its access is narrowed accordingly -- `libraryhub_tenant_app` loses the grant. The
role never needed the view, and holding it meant a tenant-scoped transaction could
read across tenants through it.

One latent fault is fixed while the view is being rewritten: it joined
`control.organizations` on `tenant_id`, which duplicates every copy the day a
tenant has two organizations. It now joins through the holding's branch, which is
what actually determines the owner.

Refusing rather than guessing
-----------------------------
The migration raises if any ITEM entity has no tenant counterpart. The check
already said zero, but a migration that deletes identity rows should enforce the
condition it depends on rather than trust a report from earlier in the day.

Downgrade, honestly
-------------------
The tables are recreated empty and the old view and check constraint are restored.
The rows are not: they were dropped. `_legacy_items_backup.sql` in the workspace
holds a `pg_dump --data-only` of all three tables taken before this ran.

Revision ID: b1c4e8f29a37
Revises: a9b2d5f81e46
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b1c4e8f29a37"
down_revision: Union[str, Sequence[str], None] = "a9b2d5f81e46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENTITY_TYPES_WITHOUT_ITEM = (
    "PERSON",
    "ORGANIZATION",
    "CONCEPT",
    "WORK",
    "EXPRESSION",
    "MANIFESTATION",
    "PLACE",
    "TIME_SPAN",
    "CLASSIFICATION",
)

TENANT_SETTING = "nullif(current_setting('libraryhub.tenant_id', true), '')::uuid"


def _entity_type_check(values) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"check (entity_type in ({rendered}))"


TENANT_ITEM_IDENTIFIERS = """
create table tenant.item_identifiers (
    id uuid primary key,
    tenant_id uuid not null,
    item_id uuid not null
        references tenant.items (id) on delete cascade,
    scheme varchar(100) not null,
    value varchar(500) not null,
    qualifier varchar(300),
    preferred boolean not null default false,
    created_at timestamptz not null default now(),
    constraint uq_item_identifiers_tenant_scheme_value
        unique (tenant_id, scheme, value)
)
"""

# The projection, not a shim. Owner-invoked on purpose: that is what lets a
# reader outside any tenant see every institution's copies.
VIEW_WITHOUT_LEGACY = """
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
left join control.branches b on b.id = th.branch_id
left join control.organizations co on co.id = b.organization_id
"""

# Same reasoning as items_compat: a copy's identifiers are tenant data, and this
# is how a global reader sees them without a tenant context of its own.
VIEW_ITEM_IDENTIFIERS = """
create view public.item_identifiers as
select
    ii.id,
    coalesce(item.legacy_entity_id, item.id) as entity_id,
    ii.scheme,
    ii.value,
    ii.qualifier,
    ii.preferred
from tenant.item_identifiers ii
join tenant.items item on item.id = ii.item_id
"""

# The shape before this revision, restored on downgrade so the migration can be
# reversed even though the rows cannot.
VIEW_WITH_LEGACY = """
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
    select 1 from tenant.items ti2 where ti2.legacy_entity_id = li.entity_id
)
"""


def upgrade() -> None:
    # ---------------------------------------------------------- 1. new home
    op.execute(TENANT_ITEM_IDENTIFIERS)

    op.execute(
        "alter table tenant.item_identifiers enable row level security"
    )
    op.execute(
        "alter table tenant.item_identifiers force row level security"
    )
    op.execute(
        "create policy tenant_isolation on tenant.item_identifiers "
        f"using (tenant_id = {TENANT_SETTING}) "
        f"with check (tenant_id = {TENANT_SETTING})"
    )

    # Carried across before the entities that own them are deleted; the foreign
    # key from identifiers to entities cascades.
    op.execute(
        """
        INSERT INTO tenant.item_identifiers
            (id, tenant_id, item_id, scheme, value, qualifier, preferred)
        SELECT
            gen_random_uuid(),
            ti.tenant_id,
            ti.id,
            i.scheme,
            i.value,
            i.qualifier,
            COALESCE(i.preferred, false)
        FROM public.identifiers i
        JOIN public.entities e
          ON e.id = i.entity_id AND e.entity_type = 'ITEM'
        JOIN tenant.items ti ON ti.legacy_entity_id = i.entity_id
        """
    )

    # ------------------------------------------- 2. global projections
    op.execute("drop view if exists public.items_compat")
    op.execute(VIEW_WITHOUT_LEGACY)
    op.execute(VIEW_ITEM_IDENTIFIERS)

    op.execute(
        "grant select on public.items_compat, public.item_identifiers "
        "to libraryhub_global_app"
    )
    op.execute(
        "revoke all on public.items_compat, public.item_identifiers "
        "from libraryhub_tenant_app"
    )

    # ------------------------------------------- 3. the legacy tables go
    op.execute("drop table if exists public.item_agent_relation")
    op.execute("drop table if exists public.manifestation_item")
    op.execute("drop table if exists public.items")

    # ------------------------------------------- 4. the ITEM vocabulary goes
    op.execute(
        """
        DO $$
        DECLARE
            orphans integer;
        BEGIN
            SELECT count(*) INTO orphans
            FROM public.entities e
            WHERE e.entity_type = 'ITEM'
              AND NOT EXISTS (
                  SELECT 1 FROM tenant.items ti
                  WHERE ti.legacy_entity_id = e.id
              );

            IF orphans > 0 THEN
                RAISE EXCEPTION
                    '% ITEM entities have no tenant counterpart; refusing to '
                    'delete identity rows that would be lost', orphans;
            END IF;
        END
        $$
        """
    )

    op.execute("delete from public.entities where entity_type = 'ITEM'")

    op.execute(
        "alter table public.entities "
        "drop constraint if exists ck_entities_entity_type"
    )
    op.execute(
        "alter table public.entities add constraint ck_entities_entity_type "
        + _entity_type_check(ENTITY_TYPES_WITHOUT_ITEM)
    )

    op.execute(
        "grant select on tenant.item_identifiers to libraryhub_tenant_app"
    )


def downgrade() -> None:
    op.execute(
        "alter table public.entities "
        "drop constraint if exists ck_entities_entity_type"
    )
    op.execute(
        "alter table public.entities add constraint ck_entities_entity_type "
        + _entity_type_check(ENTITY_TYPES_WITHOUT_ITEM + ("ITEM",))
    )

    # Recreated empty. The data was dropped with them; see the module docstring.
    op.execute(
        """
        create table public.items (
            entity_id uuid primary key
                references public.entities (id) on delete cascade,
            barcode varchar(200),
            shelfmark varchar(500),
            condition varchar(100),
            availability_status varchar(100),
            notes text
        )
        """
    )

    op.execute(
        """
        create table public.manifestation_item (
            manifestation_entity_id uuid not null
                references public.manifestations (entity_id) on delete cascade,
            item_entity_id uuid not null unique
                references public.items (entity_id) on delete cascade
        )
        """
    )

    op.execute(
        """
        create table public.item_agent_relation (
            item_entity_id uuid not null
                references public.items (entity_id) on delete cascade,
            agent_entity_id uuid not null
                references public.entities (id) on delete cascade,
            role varchar(100) not null,
            primary key (item_entity_id, agent_entity_id, role)
        )
        """
    )

    op.execute("drop view if exists public.item_identifiers")
    op.execute("drop view if exists public.items_compat")
    op.execute(VIEW_WITH_LEGACY)

    op.execute(
        "grant select on public.items_compat to libraryhub_tenant_app"
    )

    op.execute("drop table if exists tenant.item_identifiers")
