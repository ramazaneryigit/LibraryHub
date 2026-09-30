"""close the update half of the account guard

The hole
--------
`control.users` carries a trigger that stops an application role from creating an
administrator account, or an account that is already verified. It was declared
`BEFORE INSERT` only.

The application role holds `INSERT, SELECT, UPDATE` on that table -- the grant is
real and deliberate, and it is what lets the panel manage staff at all. So the
guard was the boundary, not the grant, and it covered one of the two ways in. An
`UPDATE` could:

* set `role = 'admin'` on an existing account, which is the escalation the INSERT
  guard exists to prevent, one statement later;
* rewrite an administrator's `password_hash`, which is account takeover without
  ever touching `role`.

Nothing does either today, because nothing updated this table through the
application. Adding staff management to the API is exactly the change that would
have made it reachable, which is why this comes first.

What the guard now says
-----------------------
An application role may not touch an administrator account, in either direction:
`new.role = 'admin'` covers promotion and any edit to an admin row, and
`old.role = 'admin'` covers demotion. Everything else about an ordinary account
stays editable, because that is the point of the panel.

The `email_verified_at` rule stays INSERT-only on purpose. Verifying an address is
an UPDATE, it is what `/auth/verify-email` legitimately does, and extending that
rule would have broken the one flow it exists to protect.

Renamed
-------
`guard_self_registration` became `guard_application_account_writes`. It no longer
guards registration; it constrains what an application role may do to accounts at
all, and a name that says otherwise is how the next person concludes the UPDATE
path is unguarded.

Revision ID: a7c3e9f14d26
Revises: f5b2c8d36a94
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a7c3e9f14d26"
down_revision: Union[str, Sequence[str], None] = "f5b2c8d36a94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GUARD = """
create or replace function control.guard_application_account_writes()
returns trigger
language plpgsql
as $function$
begin
    -- The owner runs administrative scripts and may write whatever it is asked
    -- to write. Tested with `rolsuper`: a superuser is a member of *every* role,
    -- so a `pg_has_role` membership test returns true for the owner as well and
    -- constrains exactly the account it means to exempt.
    if exists (
        select 1 from pg_roles where rolname = current_user and rolsuper
    ) then
        return new;
    end if;

    -- Both directions. `new.role` catches a promotion and any edit at all to an
    -- administrator row -- including a password reset, which is account takeover
    -- without ever touching the role. `old.role` catches a demotion.
    if new.role = 'admin'
       or (tg_op = 'UPDATE' and old.role = 'admin')
    then
        raise exception
            'an application role cannot touch an administrator account';
    end if;

    -- INSERT only: verifying an address is an UPDATE, and that is what the
    -- verification flow legitimately does.
    if tg_op = 'INSERT' and new.email_verified_at is not null then
        raise exception
            'an account cannot be created already verified';
    end if;

    return new;
end;
$function$;
"""


PREVIOUS = """
create or replace function control.guard_self_registration()
returns trigger
language plpgsql
as $function$
begin
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


def upgrade() -> None:
    op.execute("drop trigger if exists users_guard_self_registration on control.users")
    op.execute(GUARD)
    op.execute(
        "create trigger users_guard_application_account_writes "
        "before insert or update on control.users "
        "for each row execute function control.guard_application_account_writes()"
    )
    op.execute("drop function if exists control.guard_self_registration()")


def downgrade() -> None:
    op.execute(
        "drop trigger if exists "
        "users_guard_application_account_writes on control.users"
    )
    op.execute(PREVIOUS)
    op.execute(
        "create trigger users_guard_self_registration "
        "before insert on control.users "
        "for each row execute function control.guard_self_registration()"
    )
    op.execute(
        "drop function if exists control.guard_application_account_writes()"
    )
