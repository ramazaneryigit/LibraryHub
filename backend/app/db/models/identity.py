"""Entities, identifiers and merge history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

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
