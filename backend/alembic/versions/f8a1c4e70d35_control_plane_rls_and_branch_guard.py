"""close the control-plane and branch-ownership gaps

Two holes, both of the same kind: a rule that lives in application code instead of
in the database.

`control.branches` had no policy
--------------------------------
Every `tenant.*` table has a `tenant_isolation` policy and a tenant-scoped
transaction cannot see another institution's rows. `control.branches` was left
without one, so while the rest of the control plane was hardened this table stayed
readable in full. Nothing exploits it today -- the only reader is the branch check
in the tenant router, which runs inside a tenant session -- but "nothing reads it
yet" is a property of today's code, not of the schema.

No API endpoint reads `control.branches` outside a tenant transaction (checked),
so enabling the policy changes nothing that currently works. The owner is a
superuser and bypasses it, which is what keeps the administrative scripts working.

The foreign key was never a check of ownership
----------------------------------------------
`fk_holdings_branch` confirms the branch exists. It does not confirm the branch is
yours, and foreign key validation runs outside row level security, so an
institution could attach a holding to another institution's branch and every
constraint would be satisfied. The application check in `_assert_branch_is_ours`
catches that on the paths that call it; the trigger catches it on the paths that
do not, including a future bulk import nobody has written yet.

The trigger is not `security definer` on purpose: it must read `control.branches`
*as the caller*, so the policy is what decides whether the branch is visible.

Grants
------
`libraryhub_tenant_app` still held `SELECT` on `control.email_verifications` and
`control.organization_domains`, inherited from the schema-wide default privilege
set in Aşama 3. A tenant transaction has no business reading verification
challenges or domain claims at all, so both are revoked.

Revision ID: f8a1c4e70d35
Revises: e7f0b3d69c24
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f8a1c4e70d35"
down_revision: Union[str, Sequence[str], None] = "e7f0b3d69c24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same expression as the policies on tenant.*, and for the same reason: it is
# fail-closed. With no value bound, `current_setting(..., true)` returns NULL, the
# comparison is NULL, and no rows are visible.
TENANT_SETTING = "nullif(current_setting('libraryhub.tenant_id', true), '')::uuid"


GUARD_FUNCTION = f"""
create or replace function tenant.assert_branch_belongs_to_tenant()
returns trigger
language plpgsql
as $$
declare
    owning_tenant uuid;
begin
    select b.tenant_id into owning_tenant
    from control.branches b
    where b.id = new.branch_id;

    if owning_tenant is null or owning_tenant <> new.tenant_id then
        raise exception
            'branch % does not belong to the tenant that owns this row',
            new.branch_id
            using errcode = 'check_violation';
    end if;

    return new;
end;
$$;
"""


def upgrade() -> None:
    op.execute("alter table control.branches enable row level security")
    op.execute("alter table control.branches force row level security")

    op.execute(
        "create policy tenant_isolation on control.branches "
        f"using (tenant_id = {TENANT_SETTING}) "
        f"with check (tenant_id = {TENANT_SETTING})"
    )

    op.execute(GUARD_FUNCTION)

    for table in ("holdings", "locations"):
        op.execute(
            f"create trigger {table}_branch_tenant_guard "
            f"before insert or update of branch_id on tenant.{table} "
            "for each row execute function "
            "tenant.assert_branch_belongs_to_tenant()"
        )

    op.execute(
        "revoke select on control.email_verifications, "
        "control.organization_domains from libraryhub_tenant_app"
    )


def downgrade() -> None:
    op.execute(
        "grant select on control.email_verifications, "
        "control.organization_domains to libraryhub_tenant_app"
    )

    for table in ("holdings", "locations"):
        op.execute(
            f"drop trigger if exists {table}_branch_tenant_guard "
            f"on tenant.{table}"
        )

    op.execute(
        "drop function if exists tenant.assert_branch_belongs_to_tenant()"
    )

    op.execute("drop policy if exists tenant_isolation on control.branches")
    op.execute("alter table control.branches no force row level security")
    op.execute("alter table control.branches disable row level security")
