"""Candidate matches and the decisions taken on them."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["ReconciliationCandidate", "ReconciliationDecision"]


class ReconciliationCandidate(Base):
    __tablename__ = "reconciliation_candidates"

    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "candidate_entity_id",
            name="uq_reconciliation_candidate",
        ),
        CheckConstraint(
            "score >= 0.0 AND score <= 1.0",
            name="ck_reconciliation_candidate_score",
        ),
        Index(
            "ix_reconciliation_candidates_source_score",
            "source_record_id",
            "score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "source_records.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    candidate_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    evidence: Mapped[dict | list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class ReconciliationDecision(Base):
    __tablename__ = "reconciliation_decisions"

    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            name="uq_reconciliation_decision_source_record",
        ),
        CheckConstraint(
            "status IN ('accepted', 'rejected', 'unresolved', 'new_entity')",
            name="ck_reconciliation_decision_status",
        ),
        CheckConstraint(
            "origin IN ('manual', 'automatic')",
            name="ck_reconciliation_decision_origin",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_reconciliation_decision_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "source_records.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "reconciliation_candidates.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    evidence_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unresolved",
    )

    origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="automatic",
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    decision_method: Mapped[str | None] = mapped_column(
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
