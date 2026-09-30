"""staff accounts and server-side sessions

Why this is the prerequisite for Aşama 5
----------------------------------------
`POST /items` cannot move to the Tenant Data Plane until the request knows which
tenant it belongs to. There is no honest default: picking one silently would
file every new copy under whichever library happened to be first, and the
`WITH CHECK` half of the row level security policy would in any case refuse the
write. So the tenant has to come from an authenticated identity, which is what
this migration makes possible.

The connection
--------------
`control.users.tenant_id` is the single source of the tenant for a request. The
dependency `tenant_db` binds it into `libraryhub.tenant_id`, and the policies on
`tenant.*` do the isolation. The client is never asked which library it is
acting for -- accepting that from a request would be the entire vulnerability.

Sessions are rows, not signed tokens
------------------------------------
A signed token validates itself and therefore cannot be withdrawn without a
denylist. Libraries need revocation from day one (staff leave, a laptop goes
missing), so the session is a row with a `revoked_at`. Only the SHA-256 of the
token is stored.

Grants
------
`libraryhub_tenant_app` gains the ability to read accounts and to create and
revoke its own sessions. It deliberately still cannot *create* users: that is an
administrative act and is done with the owner credential by
`scripts/create_user.py`. There is no row level security on these two tables --
a session belongs to a user rather than to a tenant, and access is decided by
knowing the token, which is looked up by hash.

Revision ID: d6e9a2c58b13
Revises: c5d8f1b69a07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e9a2c58b13"
down_revision: Union[str, Sequence[str], None] = "c5d8f1b69a07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("password_hash", sa.String(length=300), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["control.tenants.id"],
            name="fk_users_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'librarian', 'viewer')",
            name="ck_users_role",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema="control",
    )

    op.create_index(
        "ix_users_tenant_id",
        "users",
        ["tenant_id"],
        schema="control",
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["control.users.id"],
            name="fk_sessions_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema="control",
    )

    op.create_index(
        "ix_sessions_user_id",
        "sessions",
        ["user_id"],
        schema="control",
    )

    # Login has to read the account and write a session, so the application role
    # needs exactly that and nothing more.
    op.execute("grant usage on schema control to libraryhub_tenant_app")
    op.execute("grant select on control.users to libraryhub_tenant_app")
    op.execute(
        "grant select, insert, update on control.sessions "
        "to libraryhub_tenant_app"
    )


def downgrade() -> None:
    op.execute(
        "revoke select, insert, update on control.sessions "
        "from libraryhub_tenant_app"
    )
    op.execute("revoke select on control.users from libraryhub_tenant_app")

    op.drop_index("ix_sessions_user_id", table_name="sessions", schema="control")
    op.drop_table("sessions", schema="control")

    op.drop_index("ix_users_tenant_id", table_name="users", schema="control")
    op.drop_table("users", schema="control")
