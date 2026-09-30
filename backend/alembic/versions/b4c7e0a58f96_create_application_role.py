"""create the non-superuser application login role

Why this exists
---------------
Aşama 3 created row level security policies on `tenant.*`, but the application
still connected as the database owner -- and in the official postgres image
`POSTGRES_USER` is a superuser, which bypasses RLS entirely. The policies were
correct and completely inert (docs/architecture-v2.md §0.7).

This migration creates the login role the application actually uses:

* `NOSUPERUSER` and `NOBYPASSRLS`, so policies apply to it;
* `NOCREATEDB` / `NOCREATEROLE`, so it is not an administrative role;
* a member of `libraryhub_global_app` and `libraryhub_tenant_app`, which carry
  the plane privileges.

Membership is granted `WITH INHERIT TRUE` explicitly. PostgreSQL 16 changed the
default for `GRANT role TO role` to `INHERIT FALSE, SET TRUE`, so without the
explicit option the application role would hold the grants but not inherit them,
and every query would fail until the code called `SET ROLE`.

Where the credentials come from
-------------------------------
`APP_DATABASE_URL`, not a literal in this file, so the password lives in exactly
one place: the gitignored `.env`. The role name must be a plain lowercase
identifier and the password is single-quote escaped, because PostgreSQL does not
accept bind parameters in DDL. Nothing secret is logged by this migration, but a
server configured with `log_statement = 'ddl'` would record the statement.

Re-running is safe: the create is guarded and the alter repairs a role that was
created without the intended attributes. Changing the password is a matter of
updating `.env` and running `ALTER ROLE` (documented in docs/architecture-v2.md
Ek C).

Revision ID: b4c7e0a58f96
Revises: a3b6d9f47e85
"""

import os
import re
from typing import Sequence, Union

from alembic import op
from sqlalchemy.engine import make_url


revision: str = "b4c7e0a58f96"
down_revision: Union[str, Sequence[str], None] = "a3b6d9f47e85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLANE_ROLES = ("libraryhub_global_app", "libraryhub_tenant_app")

SAFE_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\Z")


def _application_credentials():
    """Return (username, password) for the application role.

    Returns None when the configured URL is not PostgreSQL, which is the case in
    the SQLite test environment where this migration never runs anyway.
    """

    raw = os.environ.get("APP_DATABASE_URL")

    if not raw:
        raise RuntimeError(
            "APP_DATABASE_URL must be set so this migration knows which "
            "application role to create. docker-compose.yml sets it for both "
            "the migrate and api services."
        )

    url = make_url(raw)

    if url.get_backend_name() != "postgresql":
        return None

    if not url.username or not url.password:
        raise RuntimeError(
            "APP_DATABASE_URL must contain both a username and a password"
        )

    if not SAFE_IDENTIFIER.match(url.username):
        raise RuntimeError(
            "APP_DATABASE_URL username must be a plain lowercase identifier, "
            f"got {url.username!r}"
        )

    return url.username, url.password


def upgrade() -> None:
    credentials = _application_credentials()

    if credentials is None:
        return

    username, password = credentials

    # PostgreSQL does not accept parameters in DDL, so the password is escaped
    # for a string literal instead.
    password_literal = "'" + password.replace("'", "''") + "'"

    op.execute(
        f"""
        do $$
        begin
            if not exists (select 1 from pg_roles where rolname = '{username}') then
                create role {username} login;
            end if;
        end
        $$;
        """
    )

    op.execute(
        f"alter role {username} with login "
        f"nosuperuser nocreatedb nocreaterole nobypassrls "
        f"password {password_literal}"
    )

    for role in PLANE_ROLES:
        op.execute(f"grant {role} to {username} with inherit true, set true")


def downgrade() -> None:
    credentials = _application_credentials()

    if credentials is None:
        return

    username, _ = credentials

    # The API may still be connected as this role. Terminating those backends
    # first makes the drop deterministic rather than failing part way through.
    op.execute(
        f"""
        select pg_terminate_backend(pid)
        from pg_stat_activity
        where usename = '{username}' and pid <> pg_backend_pid()
        """
    )

    for role in PLANE_ROLES:
        op.execute(f"revoke {role} from {username}")

    op.execute(f"drop owned by {username}")
    op.execute(f"drop role if exists {username}")
