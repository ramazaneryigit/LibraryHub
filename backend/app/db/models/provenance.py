"""Provenance: which source said a value, and who decided it.

§6 decided that every value has a source. `SourceSystem` was built for that in
Aşama 1 and lives in `sources.py` with its `trust_level` policy; it stayed empty
because nothing wrote assertions. `FieldAssertion` is what writes them, and it is
the one place all five participants -- libraries, academicians, publishers, the
ISBN agency, vendors -- say "I claim this".

`SourceSystem` is deliberately *not* redefined here. It already exists, and a
second definition of one table is not a style question: SQLAlchemy raises at
import, the whole application fails to load, and it takes every test with it.
That is how this file was written the first time.

A model rather than a bare table, for the reason recorded on `outbox_events`:
without one `alembic check` proposes to drop the table on every run, and a warning
people learn to ignore is how real drift gets through.

The server defaults and the guard trigger live in migration `a4c7e2b91f38`.
Repeating the defaults here would put PostgreSQL-only expressions into DDL the
SQLite test engine executes, and it refuses them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import REAL, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from ..base import Base
from ...core.ids import uuid7

__all__ = ["AuthorityCandidate", "FieldAssertion"]


class AuthorityCandidate(Base):
    """Two names that look alike, waiting for somebody to say whether they are.

    `authority.suggest` refuses to merge on a spelling resemblance, and that rule
    only works if the resemblance has somewhere to go. This is that place: nothing
    in the catalogue changes, a row appears, and a person decides.

    Strong evidence never lands here -- it is acted on immediately -- so a row in
    this table always means "a person is needed", which is what makes the queue
    worth reading.
    """

    __tablename__ = "authority_candidates"

    __table_args__ = (
        # Both are partial, and both are declared here as well as in the migration:
        # an index the model does not know about is one the next autogenerate
        # proposes to drop.
        Index(
            "uq_authority_candidates_open",
            text("lower(incoming_name)"),
            "candidate_entity_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_authority_candidates_open",
            "status",
            text("score DESC"),
            postgresql_where=text("status = 'open'"),
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    incoming_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Kept although nothing reads it yet: it is what the name folds to, and the
    # next person to widen the matching will want it rather than re-deriving it.
    incoming_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        type_=Uuid,
    )

    candidate_name: Mapped[str] = mapped_column(Text, nullable=False)

    score: Mapped[float] = mapped_column(REAL, nullable=False)
    strength: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    source_system_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_systems.id"),
        nullable=True,
        type_=Uuid,
    )

    status: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FieldAssertion(Base):
    """One field, one value, one source.

    Not a replacement for `tenant.change_proposals`. A proposal is a *workflow* --
    rationale, evidence, withdrawal, review; an assertion is *data*. The first
    produces the second.
    """

    __tablename__ = "field_assertions"

    __table_args__ = (
        Index(
            "ix_field_assertions_entity",
            "entity_id",
            "field",
            text("asserted_at desc"),
        ),
        Index("ix_field_assertions_source", "source_system_id", "status"),
        # Partial: the review queue only ever reads open claims, and it is the
        # one query that has to stay fast as the table grows.
        Index(
            "ix_field_assertions_open",
            "status",
            text("asserted_at desc"),
            postgresql_where=text("status = 'proposed'"),
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        type_=Uuid,
    )

    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)

    # A claim can be a string, a date, a list of contributors. JSON rather than
    # text so the reviewer sees the shape the field actually takes.
    value: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    source_system_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_systems.id"),
        nullable=False,
        type_=Uuid,
    )

    asserted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    asserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(Text, nullable=False)

    # `REAL`, matching the migration exactly. Declaring a bare float makes
    # SQLAlchemy infer DOUBLE PRECISION, and then `alembic check` spends the rest
    # of the project's life proposing to alter a column that is already correct.
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
