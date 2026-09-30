"""ORM models, grouped by domain.

Imported for their side effect as much as for their names: each module registers
tables on `Base.metadata`, and Alembic's autogenerate compares that metadata
against the database. A model module nobody imports is a table Alembic believes
should be dropped.

The re-exports keep call sites to a single import: `from app.db.models import
Work` rather than a path per domain. Each module declares `__all__`, so the star
imports here bring in the model classes and nothing else.
"""

from .agents import *  # noqa: F401,F403
from .authorities import *  # noqa: F401,F403
from .bibliographic import *  # noqa: F401,F403
from .classifications import *  # noqa: F401,F403
from .control import *  # noqa: F401,F403
from .identity import *  # noqa: F401,F403
from .ingestion import *  # noqa: F401,F403
from .reconciliation import *  # noqa: F401,F403
from .relations import *  # noqa: F401,F403
from .sources import *  # noqa: F401,F403
from .tenant import *  # noqa: F401,F403
