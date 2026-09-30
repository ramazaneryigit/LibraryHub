"""self-service accounts: account kinds, domain mapping, email verification

Who this is for
---------------
Two populations with different evidence:

* **Kütüphaneciler ve akademisyenler** arrive on an academic domain. Being
  issued `@kku.edu.tr` is itself the proof of affiliation, so the address only
  has to be shown to receive mail.
* **Yayınevi ve organizasyon sorumluları** arrive on a corporate domain, where
  nothing is proved by the address alone -- anybody can register a domain. The
  domain therefore has to be claimed for the organization, and `verified_at` /
  `verification_method` record that it was and how.

Both end up at the same gate. `control.organization_domains` maps a domain to an
organization, and an account can only be created on a domain that is already
there. That is deliberate: a librarian can only manage the holdings of a library
that is in the system, so the institution has to be onboarded first. Onboarding
a domain is an administrative act with a script, not something an email address
can do about itself.

Why the account row is created before it is verified
----------------------------------------------------
The pending account exists, carries its tenant and its kind, and cannot be
logged into because `email_verified_at` is NULL. `uq_users_email` therefore
holds the address from the first request, and verifying is one UPDATE instead of
a second insert that could fail after a token had already been spent.

Guard against self-assigned privilege
-------------------------------------
Registration is now open to anyone with a qualifying address, so the insert
itself has to be constrained: an application role may not create an
administrator, and may not create an account that is already verified. The
trigger fires only for the application roles -- `scripts/create_user.py` runs as
the owner and stays unrestricted, because an administrator creating an
administrator is the normal case.

Grants move to the global role
------------------------------
Identity is a global-plane concern, so `control.users`, `control.sessions` and
`control.email_verifications` are read and written through
`libraryhub_global_app`. The previous revision had put the session grants on
`libraryhub_tenant_app`, which meant a tenant-scoped transaction -- now that
`tenant_session` drops to that role -- could still mint sessions. Revoking them
restores the point of the split: inside a tenant transaction, only tenant data
is writable.

Revision ID: e7f0b3d69c24
Revises: d6e9a2c58b13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f0b3d69c24"
down_revision: Union[str, Sequence[str], None] = "d6e9a2c58b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GUARD_FUNCTION = """
create or replace function control.guard_self_registration()
returns trigger
language plpgsql
as $$
begin
    -- Only the application roles are constrained. The owner runs administrative
    -- scripts and may create whatever it is asked to create.
    if not pg_has_role(current_user, 'libraryhub_global_app', 'MEMBER') then
        return new;
    end if;

    if new.role = 'admin' then
        raise exception
            'an application role cannot create an administrator account';
    end if;

    if new.email_verified_at is not null then
        raise exception
            'an account cannot be created already verified';
    end if;

    return new;
end;
$$;
"""


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "account_kind",
            sa.String(length=30),
            nullable=False,
            server_default="institutional",
        ),
        schema="control",
    )

    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="control",
    )

    op.create_check_constraint(
        "ck_users_account_kind",
        "users",
        "account_kind IN ('institutional', 'corporate')",
        schema="control",
    )

    # Accounts that already exist were created by an administrator, so they are
    # verified by construction rather than by a round trip.
    op.execute(
        "update control.users "
        "set email_verified_at = created_at "
        "where email_verified_at is null"
    )

    op.create_table(
        "organization_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "verification_method",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["control.organizations.id"],
            name="fk_organization_domains_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", name="uq_organization_domains_domain"),
        schema="control",
    )

    op.create_index(
        "ix_organization_domains_organization_id",
        "organization_domains",
        ["organization_id"],
        schema="control",
    )

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["control.users.id"],
            name="fk_email_verifications_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_email_verifications_token_hash",
        ),
        schema="control",
    )

    op.create_index(
        "ix_email_verifications_user_id",
        "email_verifications",
        ["user_id"],
        schema="control",
    )

    # Identity belongs to the global plane.
    op.execute("grant usage on schema control to libraryhub_global_app")
    op.execute(
        "grant select on control.tenants, control.organizations, "
        "control.branches, control.organization_domains "
        "to libraryhub_global_app"
    )
    op.execute(
        "grant select, insert, update on control.users "
        "to libraryhub_global_app"
    )
    op.execute(
        "grant select, insert, update on control.sessions "
        "to libraryhub_global_app"
    )
    op.execute(
        "grant select, insert, update on control.email_verifications "
        "to libraryhub_global_app"
    )

    # ... and therefore not to the tenant role, which a tenant-scoped
    # transaction drops down to.
    op.execute(
        "revoke select, insert, update on control.sessions "
        "from libraryhub_tenant_app"
    )
    op.execute("revoke select on control.users from libraryhub_tenant_app")

    op.execute(GUARD_FUNCTION)

    op.execute(
        "create trigger users_guard_self_registration "
        "before insert on control.users "
        "for each row execute function control.guard_self_registration()"
    )


def downgrade() -> None:
    op.execute(
        "drop trigger if exists users_guard_self_registration "
        "on control.users"
    )
    op.execute("drop function if exists control.guard_self_registration()")

    op.execute(
        "revoke select, insert, update on control.email_verifications "
        "from libraryhub_global_app"
    )
    op.execute(
        "revoke select, insert, update on control.users "
        "from libraryhub_global_app"
    )
    op.execute(
        "grant select on control.users to libraryhub_tenant_app"
    )
    op.execute(
        "grant select, insert, update on control.sessions "
        "to libraryhub_tenant_app"
    )
    op.execute(
        "revoke select, insert, update on control.sessions "
        "from libraryhub_global_app"
    )
    op.execute(
        "revoke select on control.tenants, control.organizations, "
        "control.branches, control.organization_domains "
        "from libraryhub_global_app"
    )

    op.drop_index(
        "ix_email_verifications_user_id",
        table_name="email_verifications",
        schema="control",
    )
    op.drop_table("email_verifications", schema="control")

    op.drop_index(
        "ix_organization_domains_organization_id",
        table_name="organization_domains",
        schema="control",
    )
    op.drop_table("organization_domains", schema="control")

    op.drop_constraint(
        "ck_users_account_kind",
        "users",
        schema="control",
        type_="check",
    )
    op.drop_column("users", "email_verified_at", schema="control")
    op.drop_column("users", "account_kind", schema="control")
