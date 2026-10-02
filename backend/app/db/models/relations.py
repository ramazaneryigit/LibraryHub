"""The generic subject-predicate-object graph."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["EntityRelation", "RelationPredicate", "RelationPredicateConstraint", "EntityRelationQualifier"]


class EntityRelation(Base):
    __tablename__ = "entity_relation"

    __table_args__ = (
        UniqueConstraint(
            "subject_entity_id",
            "predicate",
            "object_entity_id",
            name="uq_entity_relation_subject_predicate_object",
        ),
        # Reverse direction. The unique constraint above is led by
        # subject_entity_id, so object-side lookups (concept hierarchy
        # traversal, relation listing, merge rewrites) cannot seek with it.
        # Measured ~440x slower without this index; see
        # docs/architecture-v2.md §15.1.
        Index(
            "ix_entity_relation_object_predicate_subject",
            "object_entity_id",
            "predicate",
            "subject_entity_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    subject_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    predicate: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    object_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class RelationPredicate(Base):
    __tablename__ = "relation_predicates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    code: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )

    label: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_scheme: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    inverse_predicate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("relation_predicates.id", ondelete="SET NULL"),
        nullable=True,
    )

    symmetric: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    transitive: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class RelationPredicateConstraint(Base):
    __tablename__ = "relation_predicate_constraints"

    __table_args__ = (
        UniqueConstraint(
            "predicate_id",
            "subject_entity_type",
            "object_entity_type",
            name="uq_relation_predicate_constraint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    predicate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "relation_predicates.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    subject_entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    object_entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class EntityRelationQualifier(Base):
    """Niteleme bilgisi — makale için cilt/sayı/sayfa/yıl gibi.

    Bir ilişkinin (örneğin makale ↔ dergi 'is_part_of'ilişkisinin) bibliyografik
    nitelemesidir. Bağımsız bir varlık değil, ilişkinin özelliğidir.

    Örnek: Makale X dergide "Cilt 25, Sayı 3, s. 412-431" yayımlandı:
        entity_relation = (article.id, 'is_part_of', journal.id)
        qualifier.volume = '25'
        qualifier.issue = '3'
        qualifier.pages = '412-431'
        qualifier.year = 2024
    """

    __tablename__ = "entity_relation_qualifiers"

    __table_args__ = (
        UniqueConstraint(
            "entity_relation_id",
            name="uq_entity_relation_qualifier_per_relation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_relation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entity_relation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Cilt numarası (süreli yayınlar için)
    volume: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Sayı numarası (dergi, gazete vb.)
    issue: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Sayfalar (sayfa aralığı veya tek sayfa)
    pages: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Yayım yılı (opsiyonel; sonra expression_manifestation'dan alınabilir)
    year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Ek nitelemeler (DOI, madde numarası, bölüm vb.)
    article_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    doi: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # Oluşturulma tarihi
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
