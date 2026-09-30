"""Persons, collective agents and their attributions."""

from __future__ import annotations

import uuid
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7


__all__ = ["Person", "CollectiveAgent", "WorkAgentRelation", "ExpressionAgentRelation", "ManifestationAgentRelation"]


class Person(Base):
    __tablename__ = "persons"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    canonical_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    given_name: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
    )

    family_name: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
    )

    biography: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class CollectiveAgent(Base):
    __tablename__ = "collective_agents"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    canonical_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    agent_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class WorkAgentRelation(Base):
    __tablename__ = "work_agent_relation"

    work_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    agent_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )


class ExpressionAgentRelation(Base):
    __tablename__ = "expression_agent_relation"

    expression_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expressions.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    agent_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )


class ManifestationAgentRelation(Base):
    __tablename__ = "manifestation_agent_relation"

    manifestation_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manifestations.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    agent_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
