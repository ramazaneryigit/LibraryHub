"""Source systems and the records ingested from them."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["SourceSystem", "SourceRecord"]


class SourceSystem(Base):
    """Registry of systems that supply data to LibraryHub.

    Provenance policy lives here: `trust_level` records how much a source's
    assertions should weigh during reconciliation. Deliberately separate from
    SourceRecord: one system has many records. See docs/architecture-v2.md §6.
    """

    __tablename__ = "source_systems"

    __table_args__ = (
        Index(
            "ix_source_systems_code",
            "code",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    system_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    trust_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
    )

    license: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attribution: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    base_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class SourceRecord(Base):
    __tablename__ = "source_records"

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_record_id",
            name="uq_source_record_system_record",
        ),
        Index(
            "ix_source_records_system_type",
            "source_system",
            "record_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Structured link to the source registry. Nullable on purpose: existing
    # rows keep working through the legacy `source_system` string and are
    # backfilled in a later phase (docs/architecture-v2.md §16, Aşama 2).
    source_system_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "source_systems.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    source_record_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    source_uri: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    record_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    institution_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "collective_agents.entity_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    raw_data: Mapped[dict | list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
