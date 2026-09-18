import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Entity(Base):
    __tablename__ = "entities"

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', 'EXPRESSION', 'MANIFESTATION', 'ITEM', 'PLACE', 'TIME_SPAN')",
            name="ck_entities_entity_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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


class Work(Base):
    __tablename__ = "works"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    canonical_title: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    original_title: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    original_language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class Expression(Base):
    __tablename__ = "expressions"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    expression_form: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class Manifestation(Base):
    __tablename__ = "manifestations"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    publication_statement: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    publication_date: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    edition_statement: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    carrier_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    extent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class Item(Base):
    __tablename__ = "items"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    barcode: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    shelfmark: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    condition: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    availability_status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


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


class Nomen(Base):
    __tablename__ = "nomens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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
    
    __table_args__ = (
        Index(
            "uq_nomens_entity_preferred_true",
            "entity_id",
            unique=True,
            postgresql_where=text("preferred = true"),
        ),
    )


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


class WorkExpression(Base):
    __tablename__ = "work_expression"

    work_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    expression_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expressions.entity_id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
    )


class ExpressionManifestation(Base):
    __tablename__ = "expression_manifestation"

    expression_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expressions.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    manifestation_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manifestations.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )


class ManifestationItem(Base):
    __tablename__ = "manifestation_item"

    manifestation_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manifestations.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )

    item_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.entity_id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
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


class ItemAgentRelation(Base):
    __tablename__ = "item_agent_relation"

    item_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.entity_id", ondelete="CASCADE"),
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


class EntityRelation(Base):
    __tablename__ = "entity_relation"

    __table_args__ = (
        UniqueConstraint(
            "subject_entity_id",
            "predicate",
            "object_entity_id",
            name="uq_entity_relation_subject_predicate_object",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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