"""Entities, identifiers and merge history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["EntityMerge", "Entity", "Identifier", "Nomen"]


class EntityMerge(Base):
    __tablename__ = "entity_merges"

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            name="uq_entity_merge_source",
        ),
        CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="ck_entity_merge_different_entities",
        ),
        CheckConstraint(
            "origin IN ('manual', 'automatic')",
            name="ck_entity_merge_origin",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_entity_merge_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    merge_method: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    reviewed_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class Entity(Base):
    __tablename__ = "entities"

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', 'EXPRESSION', 'MANIFESTATION', 'PLACE', 'TIME_SPAN', 'CLASSIFICATION')",
            name="ck_entities_entity_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # ------------------------------------------------------------- subtypes
    #
    # Declared for the *flush order*, not for navigation.
    #
    # Every subtype row -- `works`, `persons`, `manifestations` and the rest --
    # has a foreign key to `entities`, and the database enforces it immediately.
    # SQLAlchemy orders its INSERTs across mappers that have no `relationship()`
    # between them by mapper name, and a mapper name is its module-qualified
    # class name. While every model lived in one module that accident sorted
    # `app.models.Entity` before `app.models.Work` and the order happened to be
    # right. Splitting the models by domain renamed them to
    # `app.db.models.identity.Entity` and `app.db.models.bibliographic.Work`, the
    # sort flipped, and every create of a Work, Person, Concept, Expression,
    # Manifestation, Place, TimeSpan, CollectiveAgent or ClassificationNode
    # started failing on the foreign key.
    #
    # These relationships make the dependency explicit instead of accidental.
    # `lazy="raise"` because nothing navigates them: they exist so the unit of
    # work knows the entity must be written first, and a lazy load here would be
    # an N+1 query nobody asked for.
    works: Mapped[list["Work"]] = relationship(lazy="raise")
    expressions: Mapped[list["Expression"]] = relationship(lazy="raise")
    manifestations: Mapped[list["Manifestation"]] = relationship(lazy="raise")
    persons: Mapped[list["Person"]] = relationship(lazy="raise")
    collective_agents: Mapped[list["CollectiveAgent"]] = relationship(
        lazy="raise"
    )
    concepts: Mapped[list["Concept"]] = relationship(lazy="raise")
    places: Mapped[list["Place"]] = relationship(lazy="raise")
    time_spans: Mapped[list["TimeSpan"]] = relationship(lazy="raise")
    classification_nodes: Mapped[list["ClassificationNode"]] = relationship(
        lazy="raise"
    )


class Identifier(Base):
    __tablename__ = "identifiers"

    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "scheme",
            "value",
            name="uq_identifier_entity_scheme_value",
        ),
        Index(
            "ix_identifiers_scheme_value",
            "scheme",
            "value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheme: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    value: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    qualifier: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    preferred: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class Nomen(Base):
    __tablename__ = "nomens"

    __table_args__ = (
        Index(
            "uq_nomens_entity_preferred_true",
            "entity_id",
            unique=True,
            postgresql_where=text("preferred = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    value: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    script: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    nomen_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    preferred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
