import os
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# Two credentials, deliberately:
#
#   DATABASE_URL      the schema owner. Alembic uses it, because migrations
#                     need DDL rights.
#   APP_DATABASE_URL  a non-superuser login role. The application uses it, so
#                     that row level security on tenant.* actually applies --
#                     a superuser bypasses RLS entirely, which is what made
#                     the Aşama 3 policies inert (docs/architecture-v2.md §0.7).
#
# APP_DATABASE_URL falls back to DATABASE_URL when unset, which keeps the
# SQLite test suite and any single-credential setup working unchanged.
DATABASE_URL = os.environ["DATABASE_URL"]
APP_DATABASE_URL = os.environ.get("APP_DATABASE_URL") or DATABASE_URL

engine = create_engine(
    APP_DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Must match the policies created in migration a3b6d9f47e85.
TENANT_SETTING = "libraryhub.tenant_id"

# The role a tenant-scoped transaction runs as.
#
# `libraryhub_app` is a member of both `libraryhub_global_app` (read/write on the
# global plane) and `libraryhub_tenant_app` (read on the global plane, read/write
# on the tenant plane), and inherits the union. A tenant-scoped request must not
# carry the global write with it, so the transaction drops down to the tenant
# role outright.
#
# `SET LOCAL ROLE` switches rather than adds, so inside these transactions an
# INSERT into `public.works` is refused by PostgreSQL itself. That is the
# difference between "our code does not write to the global plane" and "our code
# cannot" -- and it is what keeps a tenant from reshaping the shared
# bibliographic record (docs/architecture-v2.md §0.14).
TENANT_ROLE = "libraryhub_tenant_app"


@contextmanager
def tenant_session(tenant_id: UUID):
    """Yield a session whose statements are scoped to one tenant.

    Every tenant-plane statement has to run with the tenant's id bound, because
    the policies on `tenant.*` compare `tenant_id` against this setting. Doing
    it here means the filtering happens in the database rather than in
    application code that could forget a `WHERE tenant_id = ...`.

    The policy is fail-closed: with no value bound, `current_setting(...)`
    returns NULL, the comparison is NULL, and **no rows are visible**. Forgetting
    the binding shows nothing rather than another tenant's data.

    `set_config(..., is_local => true)` scopes the value to the transaction, so
    it cannot leak back into the pooled connection and reach an unrelated
    request.

    The transaction also drops to `libraryhub_tenant_app` (see TENANT_ROLE), so
    it cannot write to the global plane at all -- the guarantee is a grant, not a
    convention.

    The binding is re-applied at the start of *every* transaction, not once when
    the session is opened. `SET LOCAL` is transaction-scoped, so a plain `commit()`
    in the middle of an endpoint would drop both the role and the tenant setting
    -- and the statement after that commit would quietly run unscoped. Because the
    policy fails closed the symptom is an empty result rather than a leak, which
    is exactly the kind of bug that survives a review. Registering on
    `after_begin` makes the scoping a property of the session instead of a
    property of one transaction.

    PostgreSQL only. SQLite has neither the setting nor the policies, so none of
    this is applied there and the session behaves like a plain one -- the same
    trade-off as in `retrieve_work_candidates`.
    """

    db = SessionLocal()

    bind = db.get_bind()
    is_postgres = bind is not None and bind.dialect.name == "postgresql"

    def _scope_session(session, transaction, connection):
        # Role name comes from a module constant, never from input; SET ROLE
        # takes an identifier and cannot be parameterised.
        connection.execute(text(f"set local role {TENANT_ROLE}"))

        connection.execute(
            text("select set_config(:name, :value, true)"),
            {"name": TENANT_SETTING, "value": str(tenant_id)},
        )

    if is_postgres:
        event.listen(db, "after_begin", _scope_session)

    try:
        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        if is_postgres:
            event.remove(db, "after_begin", _scope_session)

        db.close()
