"""Database engine, sessions and the ORM models.

`app.db.models` is deliberately not imported here. It pulls in every model
module, and the model modules import from this package -- so re-exporting them
would create the cycle this split exists to avoid. Callers say
`from app.db.models import Work`.

`Base` and the session helpers are re-exported, because `from app.db import Base`
is what almost every call site wants and it keeps the engine plumbing in one
place.
"""

from .base import Base, SessionLocal, engine, utcnow
from .session import TENANT_ROLE, TENANT_SETTING, get_db, tenant_session

__all__ = [
    "Base",
    "SessionLocal",
    "TENANT_ROLE",
    "TENANT_SETTING",
    "engine",
    "get_db",
    "tenant_session",
    "utcnow",
]
