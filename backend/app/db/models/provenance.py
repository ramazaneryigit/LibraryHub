"""Provenance and field-level claims."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["FieldAssertion", "FieldAssertionAudit"]


class FieldAssertion(Base):
    """Bir alanın değerinin bir kaynaktan gelen iddiası.

    Her alan (başlık, yayın tarihi, yazar, vb.) farklı kaynaklardan farklı
    değerler alabilir. Hangisi canonical oluyor, kimin iddiası, kimler
    enerji harcadı — her şey provenance'ta tutulur.

    Status:
    - proposed: henüz kabul edilmedi
    - accepted: canonical alana yazıldı
    - rejected: reddedildi
    - superseded: daha yeni assertion'u tarafından değiştirildi
    """

    __tablename__ = "field_assertions"

    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "field_name",
            "source_system_id",
            "value_text",
            name="uq_field_assertion_unique_per_source",
        ),
        Index("ix_field_assertions_entity", "entity_id"),
        Index("ix_field_assertions_source", "source_system_id"),
        Index("ix_field_assertions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    field_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    value_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    value_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    source_system_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )

    confidence: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="proposed",
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("control.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    observation_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    asserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("field_assertions.id", ondelete="SET NULL"),
        nullable=True,
    )


class FieldAssertionAudit(Base):
    """Bir assertion'ın durumundaki her değişiklik — append-only log.

    Kim kabul etti, kim reddetti, ne zaman. Denetlenebilirlik için.
    """

    __tablename__ = "field_assertion_audits"

    __table_args__ = (
        Index("ix_field_assertion_audits_assertion", "assertion_id"),
        Index("ix_field_assertion_audits_at", "changed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    assertion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("field_assertions.id", ondelete="CASCADE"),
        nullable=False,
    )

    old_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    new_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("control.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
