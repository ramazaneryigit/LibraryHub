"""The transactional outbox.

One row per change to something a search index would care about, written by a
trigger inside the same transaction as the change itself. See
docs/architecture-v2.md §9.2 for why the table exists and §0.25 for what was
built, and `scripts/run_scale_checks.py` for the property that matters: a
transaction that rolls back leaves no event behind.

A model, not just a table
-------------------------
The migration could have created this without one, and `alembic check` would then
have spent the rest of the project's life proposing to drop it -- which is a
warning people learn to ignore, and an ignored warning is how a real drift gets
through. It is also the table a future indexer has to read, and a panel screen
may well want to show the backlog.

`payload` is declared with a dialect variant rather than as `JSONB` outright. The
column is `jsonb` on PostgreSQL, and the SQLite test engine has to be able to
create this table like any other; a bare `JSONB` compiles to nothing there.

Server defaults are declared in the migration and **not** here
--------------------------------------------------------------
The columns have defaults on PostgreSQL (`gen_random_uuid()`, `now()`,
`'{}'::jsonb`) because the trigger inserts without naming them. Repeating them on
the model would put `DEFAULT (gen_random_uuid())` and `DEFAULT '{}'::jsonb` into
the DDL that the SQLite test engine executes, and it refuses both -- every test
in the suite failed at `CREATE TABLE`. Alembic does not compare server defaults
unless `compare_server_default` is set, and it is not, so leaving them out of the
model costs nothing and keeps one table creatable on two engines.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..base import Base

__all__ = ["OutboxEvent"]


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    __table_args__ = (
        # Partial: an indexer only ever asks for what it has not published yet,
        # so the index stays the size of the backlog rather than the history.
        Index(
            "ix_outbox_unpublished",
            "occurred_at",
            postgresql_where=text("published_at is null"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)

    # The table the change happened in, and the row it happened to. Not a
    # foreign key, and cannot be: the row may be gone by the time this is read.
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)

    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    # 'INSERT', 'UPDATE' or 'DELETE' -- the operation, not a semantic verb. A
    # consumer that wants "WorkMerged" reads `entity_merges`.
    event_type: Mapped[str] = mapped_column(Text, nullable=False)

    # On an update, the columns that actually moved. An indexer that only knows
    # *that* a row changed has to re-read it; one that knows what moved can
    # decide whether it needs to.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    # Set for tenant-plane changes, null for the shared record.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
