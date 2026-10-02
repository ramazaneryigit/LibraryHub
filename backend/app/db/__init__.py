"""Database engine, sessions and the ORM models.

`app.db.models` is deliberately not imported here. It pulls in every model
module, and the model modules import from this package -- so re-exporting them
would create the cycle this split exists to avoid. Callers say
`from app.db.models import Work`.

`Base` and the session helpers are re-exported, because `from app.db import Base`
is what almost every call site wants and it keeps the engine plumbing in one
place.
"""

from .base import (
    Base,
    OwnerSessionLocal,
    SessionLocal,
    engine,
    owner_engine,
    utcnow,
)
from .session import (
    TENANT_ROLE, 
    TENANT_SETTING, 
    ADMIN_MODE_SETTING,
    USER_SOURCE_SYSTEM_SETTING,
    get_db, 
    tenant_session,
    admin_session,
    principal_session,
)

__all__ = [
    "Base",
    "OwnerSessionLocal",
    "SessionLocal",
    "TENANT_ROLE",
    "TENANT_SETTING",
    "ADMIN_MODE_SETTING",
    "USER_SOURCE_SYSTEM_SETTING",
    "engine",
    "get_db",
    "owner_engine",
    "tenant_session",
    "admin_session",
    "principal_session",
    "utcnow",
]
