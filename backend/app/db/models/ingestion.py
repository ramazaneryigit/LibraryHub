"""Ingestion batches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["IngestionBatch"]


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

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
