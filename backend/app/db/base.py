"""Engine, session factory and the declarative base.

Split out of the old `app/db.py` so that the session helpers, which carry the
tenant-scoping logic, are not tangled up with engine construction. The database
URL comes from `core.config` and nowhere else.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..core.config import settings

__all__ = ["Base", "SessionLocal", "engine", "utcnow"]


engine = create_engine(
    settings.app_database_url,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
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
