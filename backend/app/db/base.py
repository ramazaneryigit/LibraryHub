"""Engine, session factory and the declarative base.

Split out of the old `app/db.py` so that the session helpers, which carry the
tenant-scoping logic, are not tangled up with engine construction. The database
URL comes from `core.config` and nowhere else.

Two engines, and why
--------------------
`engine` is the application's: a non-superuser login role, so row level security
on `tenant.*` actually applies. A superuser bypasses it entirely, and using one
for ordinary requests would make the tenant policies inert.

`owner_engine` is the schema owner's. Exactly one thing needs it -- reading
change proposals across every tenant at once. `tenant.*` is protected by policies
keyed on `libraryhub.tenant_id`, and a reviewer has no tenant to bind, so under
the application role they would see nothing at all: the policies fail closed, as
they should. That session is reachable only from the admin routes, behind
`require_admin` (docs/architecture-v2.md §0.21).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..core.config import settings

__all__ = [
    "Base",
    "OwnerSessionLocal",
    "SessionLocal",
    "engine",
    "owner_engine",
    "utcnow",
]


engine = create_engine(
    settings.app_database_url,
    pool_pre_ping=True,
)


owner_engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


OwnerSessionLocal = sessionmaker(
    bind=owner_engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Timezone-aware now, for column defaults.

    Defined once here rather than in each model module, where it had drifted into
    three identical copies.
    """

    return datetime.now(timezone.utc)
