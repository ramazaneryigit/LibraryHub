"""create Control Plane tables and backfill organizations from institutions

Architecture v2 §16 Aşama 2. Creates the four Control Plane tables in the
`control` schema and derives one tenant + organization + default branch per
existing institution.

Where the institutions come from
--------------------------------
The only institution data that exists today is `item_agent_relation`: today an
Item records who holds it through an agent relation, and `collective_agents`
carries the institution's name. `source_records.institution_entity_id` was also
checked and is NULL on every row in this database, so it contributes nothing.

The backfill deliberately does NOT filter on `role`. Roles are free text with
no constraint, and "which institution is responsible for this item" is what
makes something a library. Filtering on the literal string 'holding_institution'
would silently drop any item whose custody was recorded under another role.
In this database that matters: one item uses role 'controlled_test_holder'.

What is NOT migrated
--------------------
Items stay exactly where they are. `public.items` is not touched, no item is
rewritten, and no API contract changes. Mapping items onto holdings is Aşama 4.

Reversibility
-------------
Downgrade drops the four tables. Everything they contain is *derived* from
`item_agent_relation` + `collective_agents`, so it is recomputable by running
this migration again; no primary data is lost.

Revision ID: e1f4b7d25c63
Revises: d9e3a6c14b52
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f4b7d25c63"
down_revision: Union[str, Sequence[str], None] = "d9e3a6c14b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Deterministic, collision-free slug: a readable part derived from the name
# where the name is Latin, plus eight hex characters of the institution's own
# entity_id. The id suffix guarantees uniqueness and keeps the expression
# stable so the same value can be recomputed when linking tenants to
# organizations; for non-Latin names the readable part collapses to 'org'.
SLUG_EXPRESSION = """
    coalesce(
        nullif(
            trim(both '-' from regexp_replace(lower(canonical_name), '[^a-z0-9]+', '-', 'g')),
            ''
        ),
        'org'
    ) || '-' || substr(replace(entity_id::text, '-', ''), 1, 8)
"""


BACKFILL_SQL = f"""
with institutions as (
    select distinct
        ca.entity_id,
        ca.canonical_name,
        ca.agent_type
    from item_agent_relation iar
    join collective_agents ca on ca.entity_id = iar.agent_entity_id
),
slugged as (
    select
        entity_id,
        canonical_name,
        agent_type,
        {SLUG_EXPRESSION} as slug
    from institutions
),
new_tenants as (
    insert into control.tenants
        (id, slug, display_name, status, cluster_id, created_at, updated_at)
    select
        gen_random_uuid(), slug, canonical_name, 'active', 'primary', now(), now()
    from slugged
    returning id, slug
),
new_organizations as (
    insert into control.organizations
        (id, tenant_id, collective_agent_entity_id, name, org_type, created_at)
    select
        gen_random_uuid(), nt.id, s.entity_id, s.canonical_name, s.agent_type, now()
    from slugged s
    join new_tenants nt on nt.slug = s.slug
    returning id, tenant_id
),
new_branches as (
    -- Every organization gets one default branch now, so that a later phase
    -- can make holdings.branch_id NOT NULL without a nullable-then-backfill
    -- migration.
    insert into control.branches
        (id, tenant_id, organization_id, code, name, is_default, created_at)
    select
        gen_random_uuid(), no.tenant_id, no.id, 'MAIN', 'Main', true, now()
    from new_organizations no
    returning id
)
insert into control.tenant_databases
    (tenant_id, cluster_id, dsn_secret_ref, updated_at)
select
    nt.id, 'primary', 'env:DATABASE_URL', now()
from new_tenants nt;
"""


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cluster_id", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("data_residency", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_tenants_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        schema="control",
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("collective_agent_entity_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("org_type", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("isil", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["control.tenants.id"],
            name="fk_organizations_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collective_agent_entity_id"],
            ["collective_agents.entity_id"],
            name="fk_organizations_collective_agent",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_organizations_tenant"),
        sa.UniqueConstraint(
            "collective_agent_entity_id",
            name="uq_organizations_collective_agent",
        ),
        schema="control",
    )

    op.create_table(
        "branches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["control.tenants.id"],
            name="fk_branches_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["control.organizations.id"],
            name="fk_branches_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "code",
            name="uq_branches_tenant_code",
        ),
        schema="control",
    )

    op.create_table(
        "tenant_databases",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.String(length=100), nullable=False),
        sa.Column("dsn_secret_ref", sa.String(length=500), nullable=False),
        sa.Column("read_replica_ref", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["control.tenants.id"],
            name="fk_tenant_databases_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
        schema="control",
    )

    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    # Reverse dependency order: branches and organizations reference tenants.
    op.drop_table("tenant_databases", schema="control")
    op.drop_table("branches", schema="control")
    op.drop_table("organizations", schema="control")
    op.drop_table("tenants", schema="control")
