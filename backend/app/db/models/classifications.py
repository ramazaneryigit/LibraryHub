"""Classification schemes, nodes and their mappings."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["ClassificationNode", "WorkClassification", "ClassificationMapping", "SourceClassification", "ClassificationValidation"]


class ClassificationNode(Base):
    __tablename__ = "classification_nodes"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vocabulary_schemes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    scheme_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "vocabulary_scheme_editions.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    notation: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    notation_end: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    caption: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    parent_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classification_nodes.entity_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "scheme_id",
            "notation",
            name="uq_classification_scheme_notation",
        ),
    )


class WorkClassification(Base):
    __tablename__ = "work_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    work_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    classification_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classification_nodes.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    assigned_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "work_entity_id",
            "classification_entity_id",
            name="uq_work_classification",
        ),
    )


class ClassificationMapping(Base):
    __tablename__ = "classification_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_classification_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "classification_nodes.entity_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    target_classification_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "classification_nodes.entity_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    mapping_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    mapping_method: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source_uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    source_scheme_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    target_scheme_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    review_status: Mapped[str | None] = mapped_column(
        String(50),
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_classification_entity_id",
            "target_classification_entity_id",
            "mapping_type",
            name="uq_classification_mapping",
        ),
        CheckConstraint(
            "mapping_type IN "
            "('exact_match', 'close_match', 'broad_match', "
            "'narrow_match', 'related_match')",
            name="ck_classification_mapping_type",
        ),
        CheckConstraint(
            "confidence IS NULL OR "
            "(confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_classification_mapping_confidence",
        ),
        CheckConstraint(
            "source_classification_entity_id "
            "<> target_classification_entity_id",
            name="ck_classification_mapping_not_self",
        ),
    )


class SourceClassification(Base):
    __tablename__ = "source_classifications"

    __table_args__ = (
        UniqueConstraint(
            "work_entity_id",
            "institution_entity_id",
            "scheme_id",
            "notation",
            "source_record_id",
            name="uq_source_classification_observation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    work_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    institution_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collective_agents.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vocabulary_schemes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    scheme_edition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "vocabulary_scheme_editions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    notation: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    source_record_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source_uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class ClassificationValidation(Base):
    __tablename__ = "classification_validations"

    __table_args__ = (
        UniqueConstraint(
            "source_classification_id",
            name="uq_classification_validation_source",
        ),
        CheckConstraint(
            "status IN ('valid', 'warning', 'probable_error', 'unresolved')",
            name="ck_classification_validation_status",
        ),
        CheckConstraint(
            "origin IN ('manual', 'automatic')",
            name="ck_classification_validation_origin",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_classification_validation_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_classification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "source_classifications.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unresolved",
    )
    
    origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="automatic"
    )

    warning_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    suggested_classification_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "classification_nodes.entity_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    validation_method: Mapped[str | None] = mapped_column(
        String(100),
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
