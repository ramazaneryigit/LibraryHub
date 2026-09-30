"""fix the owner exemption in the self-registration guard

The bug
-------
`control.guard_self_registration()` opens with:

    if not pg_has_role(current_user, 'libraryhub_global_app', 'MEMBER') then
        return new;
    end if;

and its comment says "Only the application roles are constrained. The owner runs
administrative scripts and may create whatever it is asked to create."

That comment has never been true. The owner is a superuser, and **a superuser is
a member of every role** -- `pg_has_role('library', 'libraryhub_global_app',
'MEMBER')` returns true. So the guard did not exempt the owner; it constrained it,
and only it.

The consequence: `scripts/create_user.py` has not been able to create an account
since the guard was added. It sets `email_verified_at`, which the guard rejects
for a constrained caller, and it is the documented way to open an account.

Why the fix is `rolsuper`
-------------------------
Because that is what the comment meant. The owner already holds the credential
that can write `control.users` directly; the guard exists to stop a *stolen
application session* from minting accounts, and an application role is never a
superuser. Nothing is loosened for the roles the guard is actually about.

Revision ID: f5b2c8d36a94
Revises: e4f1a7c25b83
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f5b2c8d36a94"
down_revision: Union[str, Sequence[str], None] = "e4f1a7c25b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FIXED = """
create or replace function control.guard_self_registration()
returns trigger
language plpgsql
as $function$
begin
    -- The owner runs administrative scripts and may create whatever it is asked
    -- to create. Tested with `rolsuper` rather than `pg_has_role`: a superuser is
    -- a member of *every* role, so the membership test this used to make returned
    -- true for the owner as well and the guard constrained exactly the account it
    -- meant to exempt.
    if exists (
        select 1 from pg_roles where rolname = current_user and rolsuper
    ) then
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
$function$;
"""

ORIGINAL = """
create or replace function control.guard_self_registration()
returns trigger
language plpgsql
as $function$
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
$function$;
"""


def upgrade() -> None:
    op.execute(FIXED)


def downgrade() -> None:
    op.execute(ORIGINAL)
