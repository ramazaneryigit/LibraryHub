"""tenant change proposals

The write boundary established in the previous revisions is a grant: a
tenant-scoped transaction drops to `libraryhub_tenant_app`, which holds SELECT
and nothing else on `public`, so an institution cannot rewrite the shared
bibliographic record. That is the right default and it left a hole. An
institution that finds a wrong publication date, or a publisher's contact who
notices their own imprint is misspelled, had nowhere to say so -- and a corporate
account in particular had nothing it was allowed to do at all.

This is the way to say so.

Why here and not in `control`
-----------------------------
The proposal is the tenant's own request, so it is written from the tenant's own
transaction and carries the same fail-closed policy as every other table in this
schema. Putting it in `control` would have meant either granting the tenant role
write access to the control plane -- which is the thing the split exists to
prevent -- or having the endpoint write outside a tenant session and take the
tenant from the request body, which is the other thing it exists to prevent.

A reviewer reads across tenants with the owner credential, which bypasses row
level security. That is already how administrative acts work here.

Accepting is not applying
-------------------------
`status` records the decision, and `applied_at` / `applied_fields` record what was
actually written. They are separate because a reviewer may accept a correction in
principle while an individual field is outside the whitelist the apply step
enforces; collapsing the two would hide which fields never made it.

Revision ID: a9b2d5f81e46
Revises: f8a1c4e70d35
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b2d5f81e46"
down_revision: Union[str, Sequence[str], None] = "f8a1c4e70d35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_SETTING = "nullif(current_setting('libraryhub.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "change_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_by_email", sa.String(length=320), nullable=True),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("target_entity_type", sa.String(length=40), nullable=True),
        sa.Column("target_entity_id", sa.Uuid(), nullable=True),
        # Plain JSON rather than JSONB: the table is small, nothing queries into
        # it, and the SQLite test engine has no JSONB.
        sa.Column("field_changes", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reviewed_by", sa.String(length=320), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_fields", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('correction', 'addition', 'relation', 'other')",
            name="ck_change_proposals_type",
        ),
        sa.CheckConstraint(
            "status IN "
            "('pending', 'accepted', 'rejected', 'withdrawn', 'applied')",
            name="ck_change_proposals_status",
        ),
        sa.CheckConstraint(
            "(change_type = 'addition' AND target_entity_id IS NULL) "
            "OR (change_type <> 'addition' AND target_entity_id IS NOT NULL)",
            name="ck_change_proposals_target",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )

    op.create_index(
        "ix_change_proposals_tenant_status",
        "change_proposals",
        ["tenant_id", "status"],
        schema="tenant",
    )

    op.create_index(
        "ix_change_proposals_status",
        "change_proposals",
        ["status"],
        schema="tenant",
    )

    op.execute("alter table tenant.change_proposals enable row level security")
    op.execute("alter table tenant.change_proposals force row level security")

    op.execute(
        "create policy tenant_isolation on tenant.change_proposals "
        f"using (tenant_id = {TENANT_SETTING}) "
        f"with check (tenant_id = {TENANT_SETTING})"
    )

    # The Aşama 3 default privileges already cover new tables in this schema;
    # this is stated anyway so the requirement is visible in the migration that
    # introduced the table rather than inferred from another one.
    op.execute(
        "grant select, insert, update, delete on tenant.change_proposals "
        "to libraryhub_tenant_app"
    )


def downgrade() -> None:
    op.execute("drop policy if exists tenant_isolation on tenant.change_proposals")
    op.execute(
        "alter table tenant.change_proposals no force row level security"
    )
    op.execute(
        "alter table tenant.change_proposals disable row level security"
    )

    op.drop_index(
        "ix_change_proposals_status",
        table_name="change_proposals",
        schema="tenant",
    )
    op.drop_index(
        "ix_change_proposals_tenant_status",
        table_name="change_proposals",
        schema="tenant",
    )
    op.drop_table("change_proposals", schema="tenant")
