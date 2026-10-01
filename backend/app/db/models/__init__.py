"""ORM models, grouped by domain.

Imported for their side effect as much as for their names: each module registers
tables on `Base.metadata`, and Alembic's autogenerate compares that metadata
against the database. A model module nobody imports is a table Alembic believes
should be dropped.

On the import order
-------------------
`identity` comes first because `Entity` is the row every subtype points at, which
reads better. It is a readability choice and **not** a correctness one -- and the
distinction cost a debugging session.

Splitting these models out of one module broke every global create, because
SQLAlchemy orders INSERTs across mappers that have no relationship between them by
module-qualified class name, and the split changed those names. Reordering the
imports did not fix it. What fixed it is the nine `relationship()`s declared on
`Entity`: the dependency is now stated rather than implied by naming. See
docs/architecture-v2.md §0.19.

The re-exports keep call sites to a single import: `from app.db.models import
Work` rather than a path per domain. Each module declares `__all__`, so the star
imports here bring in the model classes and nothing else.
"""

from .identity import *  # noqa: F401,F403

from .agents import *  # noqa: F401,F403
from .authorities import *  # noqa: F401,F403
from .bibliographic import *  # noqa: F401,F403
from .classifications import *  # noqa: F401,F403
from .control import *  # noqa: F401,F403
from .ingestion import *  # noqa: F401,F403
from .outbox import *  # noqa: F401,F403
from .provenance import *  # noqa: F401,F403
from .reconciliation import *  # noqa: F401,F403
from .relations import *  # noqa: F401,F403
from .search import *  # noqa: F401,F403
from .sources import *  # noqa: F401,F403
from .tenant import *  # noqa: F401,F403
