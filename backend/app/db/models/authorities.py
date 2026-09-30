"""Places, time spans, concepts and controlled vocabularies."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["Place", "TimeSpan", "Concept", "VocabularyScheme", "VocabularySchemeEdition"]


class Place(Base):
    __tablename__ = "places"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    canonical_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    place_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class TimeSpan(Base):
    __tablename__ = "time_spans"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    begin_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    end_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class Concept(Base):
    __tablename__ = "concepts"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    preferred_label: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    definition: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    scheme: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )


class VocabularyScheme(Base):
    __tablename__ = "vocabulary_schemes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    scheme_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class VocabularySchemeEdition(Base):
    __tablename__ = "vocabulary_scheme_editions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "vocabulary_schemes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    edition: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    release_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "scheme_id",
            "edition",
            name="uq_vocabulary_scheme_edition",
        ),
    )
