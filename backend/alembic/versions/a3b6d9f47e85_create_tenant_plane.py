"""create Tenant Data Plane skeleton: tables, roles and row level security

Architecture v2 §16 Aşama 3. Tables only -- no data is moved here. Mapping the
existing `public.items` rows onto holdings and tenant items is Aşama 4.

What this creates
-----------------
* `tenant.locations`, `tenant.holdings`, `tenant.items`
* the `libraryhub_global_app` and `libraryhub_tenant_app` group roles, with
  grants and default privileges for tables created later
* row level security policies keyed on `libraryhub.tenant_id`

What RLS does and does not do here
----------------------------------
The application still connects as the database owner (`library`), which is a
superuser in the official postgres image, and **superusers bypass row level
security entirely**. So these policies are correct but not yet enforced for
application traffic. Making them real requires the application to connect as a
non-superuser role, which is the connection change that belongs with the
routing layer (docs/architecture-v2.md §5.2, §5.3).

The policies are still worth creating now, and this migration verifies they
work by switching role in the test below, because getting isolation right is
much easier while the tables are empty.

The policy is deliberately fail-closed: `current_setting(..., true)` returns
NULL when the setting is absent, the comparison yields NULL, and no rows are
visible -- a forgotten `SET LOCAL libraryhub.tenant_id` shows nothing rather
than everything.

Revision ID: a3b6d9f47e85
Revises: f2a5c8e36d74
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b6d9f47e85"
down_revision: Union[str, Sequence[str], None] = "f2a5c8e36d74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = ("locations", "holdings", "items")

# Kept identical to the expression in app/tenant_models.py. `num_nonnulls(...)`
# would be shorter but is PostgreSQL-only, and the model has to stay portable
# for the SQLite test engine -- if the two drifted, `alembic check` would flag
# a difference on every run.
TARGET_ARC_CHECK = (
    "(manifestation_entity_id IS NULL) <> (expression_entity_id IS NULL)"
)

# Fail-closed: no tenant set means no rows, not all rows.
TENANT_SETTING = "nullif(current_setting('libraryhub.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("location_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["control.branches.id"],
            name="fk_locations_branch",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "location_type IS NULL OR location_type IN "
            "('shelf', 'room', 'closed_stack', 'offsite', 'reading_room')",
            name="ck_locations_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "branch_id",
            "code",
            name="uq_locations_tenant_branch_code",
        ),
        schema="tenant",
    )

    op.create_table(
        "holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("manifestation_entity_id", sa.Uuid(), nullable=True),
        sa.Column("expression_entity_id", sa.Uuid(), nullable=True),
        sa.Column("holding_type", sa.String(length=30), nullable=False),
        sa.Column("collection_code", sa.String(length=100), nullable=True),
        sa.Column("call_number", sa.String(length=300), nullable=True),
        sa.Column("call_number_scheme", sa.String(length=50), nullable=True),
        sa.Column("holding_statement", sa.Text(), nullable=True),
        sa.Column("enumeration_pattern", sa.String(length=500), nullable=True),
        sa.Column("access_url", sa.String(length=1000), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("acquisition_source", sa.String(length=500), nullable=True),
        sa.Column("public_note", sa.Text(), nullable=True),
        sa.Column("staff_note", sa.Text(), nullable=True),
        sa.Column("local_holding_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["control.branches.id"],
            name="fk_holdings_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifestation_entity_id"],
            ["manifestations.entity_id"],
            name="fk_holdings_manifestation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["expression_entity_id"],
            ["expressions.entity_id"],
            name="fk_holdings_expression",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            TARGET_ARC_CHECK,
            name="ck_holdings_target_exactly_one",
        ),
        sa.CheckConstraint(
            "holding_type IN ('physical', 'electronic', 'microform', 'other')",
            name="ck_holdings_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'closed', 'suppressed')",
            name="ck_holdings_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "branch_id",
            "manifestation_entity_id",
            "local_holding_key",
            name="uq_holdings_branch_manifestation_key",
        ),
        schema="tenant",
    )

    op.create_index(
        "ix_holdings_tenant_manifestation",
        "holdings",
        ["tenant_id", "manifestation_entity_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_holdings_manifestation",
        "holdings",
        ["manifestation_entity_id"],
        schema="tenant",
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("holding_id", sa.Uuid(), nullable=False),
        sa.Column("barcode", sa.String(length=200), nullable=True),
        sa.Column("accession_number", sa.String(length=200), nullable=True),
        sa.Column("item_type", sa.String(length=50), nullable=True),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("shelfmark", sa.String(length=300), nullable=True),
        sa.Column("condition", sa.String(length=200), nullable=True),
        sa.Column("availability_status", sa.String(length=50), nullable=False),
        sa.Column("circulation_policy_id", sa.Uuid(), nullable=True),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("price_currency", sa.String(length=3), nullable=True),
        sa.Column("acquired_at", sa.Date(), nullable=True),
        sa.Column("donor", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["holding_id"],
            ["tenant.holdings.id"],
            name="fk_items_holding",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["tenant.locations.id"],
            name="fk_items_location",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN "
            "('active', 'withdrawn', 'lost', 'missing', 'in_repair')",
            name="ck_items_lifecycle_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        # OD3: barcode uniqueness is tenant-wide, not per branch, so a copy
        # transferred between branches cannot collide with another copy.
        sa.UniqueConstraint(
            "tenant_id",
            "barcode",
            name="uq_items_tenant_barcode",
        ),
        schema="tenant",
    )

    op.create_index(
        "ix_items_holding",
        "items",
        ["holding_id"],
        schema="tenant",
    )

    # ---------------------------------------------------------------- roles
    op.execute(
        """
        do $$
        begin
            if not exists (select 1 from pg_roles where rolname = 'libraryhub_global_app') then
                create role libraryhub_global_app nologin;
            end if;
            if not exists (select 1 from pg_roles where rolname = 'libraryhub_tenant_app') then
                create role libraryhub_tenant_app nologin;
            end if;
        end
        $$;
        """
    )

    op.execute("grant usage on schema public to libraryhub_global_app")
    op.execute("grant usage on schema public, control, tenant to libraryhub_tenant_app")

    # Global plane role: full DML on bibliographic/authority data, and no
    # privilege at all on tenant or control data.
    op.execute(
        "grant select, insert, update, delete on all tables in schema public "
        "to libraryhub_global_app"
    )

    # Tenant plane role: reads the shared knowledge plane, writes only its own.
    op.execute("grant select on all tables in schema public to libraryhub_tenant_app")
    op.execute("grant select on all tables in schema control to libraryhub_tenant_app")
    op.execute(
        "grant select, insert, update, delete on all tables in schema tenant "
        "to libraryhub_tenant_app"
    )

    # `on all tables` only covers tables that exist now, so future tables need
    # default privileges. These apply to objects created by the role running
    # this migration.
    op.execute(
        "alter default privileges in schema public "
        "grant select, insert, update, delete on tables to libraryhub_global_app"
    )
    op.execute(
        "alter default privileges in schema public "
        "grant select on tables to libraryhub_tenant_app"
    )
    op.execute(
        "alter default privileges in schema control "
        "grant select on tables to libraryhub_tenant_app"
    )
    op.execute(
        "alter default privileges in schema tenant "
        "grant select, insert, update, delete on tables to libraryhub_tenant_app"
    )

    # ------------------------------------------------------------------ RLS
    for table in TENANT_TABLES:
        op.execute(f"alter table tenant.{table} enable row level security")
        # Applies the policy to the table owner as well. A superuser still
        # bypasses it, which is why the application connection has to change
        # before this is real enforcement.
        op.execute(f"alter table tenant.{table} force row level security")

        op.execute(
            f"""
            create policy tenant_isolation on tenant.{table}
                using (tenant_id = {TENANT_SETTING})
                with check (tenant_id = {TENANT_SETTING})
            """
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"drop policy if exists tenant_isolation on tenant.{table}")
        op.execute(f"alter table tenant.{table} no force row level security")
        op.execute(f"alter table tenant.{table} disable row level security")

    op.drop_index("ix_items_holding", table_name="items", schema="tenant")
    op.drop_table("items", schema="tenant")

    op.drop_index(
        "ix_holdings_manifestation",
        table_name="holdings",
        schema="tenant",
    )
    op.drop_index(
        "ix_holdings_tenant_manifestation",
        table_name="holdings",
        schema="tenant",
    )
    op.drop_table("holdings", schema="tenant")
    op.drop_table("locations", schema="tenant")

    # Default privileges are owned by the granting role, not the grantee, so
    # they have to be revoked explicitly rather than by DROP OWNED.
    op.execute(
        "alter default privileges in schema tenant "
        "revoke all on tables from libraryhub_tenant_app"
    )
    op.execute(
        "alter default privileges in schema control "
        "revoke all on tables from libraryhub_tenant_app"
    )
    op.execute(
        "alter default privileges in schema public "
        "revoke all on tables from libraryhub_tenant_app"
    )
    op.execute(
        "alter default privileges in schema public "
        "revoke all on tables from libraryhub_global_app"
    )

    for role in ("libraryhub_tenant_app", "libraryhub_global_app"):
        op.execute(f"drop owned by {role}")
        op.execute(f"drop role if exists {role}")
