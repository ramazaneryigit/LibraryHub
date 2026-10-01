"""Work, Expression, Manifestation and the links between them."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7
from ...core.text import normalize_text


__all__ = ["Work", "Expression", "Manifestation", "WorkExpression", "ExpressionManifestation"]


class Work(Base):
    __tablename__ = "works"

    __table_args__ = (
        # Declared with text() so Alembic can see this expression index.
        # The index itself is created by migration 9f25b0d7306d using raw SQL.
        # Without this declaration `alembic check` reports it as a removed
        # index and the next `revision --autogenerate` would silently drop it.
        #
        # Known limitation: the operator class is part of the expression, so
        # Alembic logs "Cannot compare index ... assuming equal and skipping"
        # for this one index instead of comparing it. `alembic check` stays
        # clean and the index is protected from being dropped, but a future
        # divergence in its definition would not be detected. SQLAlchemy 2.0
        # looks up postgresql_ops by element key, and text()/func() expression
        # elements have key=None, so an exact compare is not achievable here.
        # See docs/architecture-v2.md §15.3.
        #
        # ddl_if(dialect="postgresql") is required, not cosmetic: SQLite has no
        # operator classes, and without this filter Base.metadata.create_all()
        # emits invalid DDL on the in-memory SQLite engine the test suite uses.
        Index(
            "ix_works_canonical_title_lower_trgm",
            text("lower(canonical_title) gin_trgm_ops"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        # The index that actually serves matching: works.normalized_title is
        # filled by the ORM event below with app.core.text.normalize_text,
        # so the stored value and the probe value are normalized identically.
        # See docs/architecture-v2.md §15.6.
        Index(
            "ix_works_normalized_title_trgm",
            text("normalized_title gin_trgm_ops"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    canonical_title: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    # Derived from canonical_title by the event listener below; never set by
    # hand. Nullable because a title with no normalizable content (for example
    # only punctuation) normalizes to None and is legitimately not comparable.
    normalized_title: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    original_title: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    original_language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    work_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


@event.listens_for(Work, "before_insert")
@event.listens_for(Work, "before_update")
def _sync_normalized_title(mapper, connection, target) -> None:
    """Keep works.normalized_title derived from canonical_title.

    Hanging this off the model instead of the router covers every write path --
    the API, the seed scripts, ingestion and anything added later -- so the
    column cannot silently drift from the title it is derived from.
    """

    target.normalized_title = normalize_text(target.canonical_title)


class Expression(Base):
    __tablename__ = "expressions"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    expression_form: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class Manifestation(Base):
    __tablename__ = "manifestations"

    __table_args__ = (
        CheckConstraint(
            "publication_status IN ('announced', 'in_press', 'published', "
            "'out_of_print', 'cancelled')",
            name="ck_manifestations_publication_status",
        ),
        # Declared so `alembic check` stops proposing to drop it. The migration
        # creates it; a partial index the model does not know about is an index
        # the next autogenerate deletes.
        Index(
            "ix_manifestations_not_yet_published",
            "publication_status",
            "publication_date",
            postgresql_where=text(
                "publication_status in ('announced', 'in_press')"
            ),
        ).ddl_if(dialect="postgresql"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    publication_statement: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    publication_date: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    edition_statement: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    carrier_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    extent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Whether the book exists yet. Defaults to `published` because every row that
    # existed before this column meant exactly that, and `publication_date` cannot
    # express the difference: "announced" is a status, not a date.
    #
    # `server_default` is a plain string, so the SQLite test engine accepts it --
    # unlike the PostgreSQL-only expressions that broke `outbox_events`. Raw SQL
    # writes do not run Python-side defaults.
    publication_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="published",
        server_default="published",
    )


class WorkExpression(Base):
    __tablename__ = "work_expression"

    work_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    expression_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expressions.entity_id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
    )


class ExpressionManifestation(Base):
    __tablename__ = "expression_manifestation"

    expression_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expressions.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    manifestation_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manifestations.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )
