import os
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
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

    PostgreSQL only. SQLite has neither the setting nor the policies, so the
    call is skipped there and this behaves like a plain session -- which is also
    how the same trade-off is handled in `retrieve_work_candidates`.
    """

    db = SessionLocal()

    try:
        bind = db.get_bind()

        if bind is not None and bind.dialect.name == "postgresql":
            db.execute(
                text("select set_config(:name, :value, true)"),
                {"name": TENANT_SETTING, "value": str(tenant_id)},
            )

        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
