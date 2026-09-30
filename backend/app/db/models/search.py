"""The derived search index.

One row per entity a search can match, holding that entity's own text and the
works a match on it resolves to. Nothing here is a source of truth: the whole
table can be dropped and rebuilt from the tables around it, which is the property
`reindex` exists to demonstrate and `run_scale_checks.py` asserts.

A model, not just a table
-------------------------
Same reason as `outbox_events`: without one, `alembic check` spends the rest of
the project's life proposing to drop the table, and a warning people learn to
ignore is how a real drift gets through.

`work_ids` is `uuid[]` on PostgreSQL, which is the right type for a GIN index and
the wrong one for the SQLite test engine, which has no array type at all. The
variant keeps the table creatable on both; nothing queries this column outside
PostgreSQL.

Server defaults are declared in the migration and not repeated here, for the
reason recorded on `outbox_events`: repeating them puts PostgreSQL-only default
expressions into DDL that SQLite executes, and it refuses them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from ..base import Base

__all__ = ["SearchDocument"]


class SearchDocument(Base):
    __tablename__ = "search_documents"

    __table_args__ = (
        # Declared with text() so Alembic can see the expression index; the index
        # itself is created by migration f3b8d1e64c72 using raw SQL.
        Index(
            "ix_search_documents_body_trgm",
            text("body gin_trgm_ops"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_search_documents_work_ids",
            "work_ids",
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index("ix_search_documents_type", "entity_type"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        type_=Uuid,
    )

    entity_type: Mapped[str] = mapped_column(Text, nullable=False)

    # What to show a reader when this document is the match.
    label: Mapped[str] = mapped_column(Text, nullable=False)

    # Everything about this entity that a probe is compared against, normalized
    # once by `app.core.text.normalize_text` at the moment it is indexed.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # The works a match on this document resolves to. A work's document points at
    # itself; a person's points at everything they wrote.
    work_ids: Mapped[list] = mapped_column(
        ARRAY(Uuid).with_variant(JSON, "sqlite"),
        nullable=False,
    )

    source_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
