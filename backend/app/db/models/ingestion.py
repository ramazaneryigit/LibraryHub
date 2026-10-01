"""Ingestion batches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["IngestionBatch"]


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    __table_args__ = (
        # The list is read newest first, and a catalogue with years of imports
        # behind it should not scan to answer "what did we load recently".
        # Declared on the model as well, because an index the model does not know
        # about is an index the next autogenerate proposes to drop.
        Index("ix_ingestion_batches_recent", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="running",
        index=True,
    )

    total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    updated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    unchanged: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # What the run could not read, and why -- named and counted rather than only
    # totalled. Counts say "416 failed"; this says which field, which is the
    # difference between a report and a complaint, and it is what a library was
    # shown before handing over its collection.
    #
    # JSON rather than a column per reason: the shape will gain fields as the
    # mapping learns to notice more, and each of those should not need a
    # migration.
    report: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
