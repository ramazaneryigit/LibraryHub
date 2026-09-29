import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)

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
        default=uuid.uuid4,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
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
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
    
class EntityMerge(Base):
    __tablename__ = "entity_merges"

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            name="uq_entity_merge_source",
        ),
        CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="ck_entity_merge_different_entities",
        ),
        CheckConstraint(
            "origin IN ('manual', 'automatic')",
            name="ck_entity_merge_origin",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_entity_merge_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "entities.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    merge_method: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
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

class Entity(Base):
    __tablename__ = "entities"

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('PERSON', 'ORGANIZATION', 'CONCEPT', 'WORK', 'EXPRESSION', 'MANIFESTATION', 'ITEM', 'PLACE', 'TIME_SPAN', 'CLASSIFICATION')",
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
class Identifier(Base):
    __tablename__ = "identifiers"

    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "scheme",
            "value",
            name="uq_identifier_entity_scheme_value",
        ),
        Index(
            "ix_identifiers_scheme_value",
            "scheme",
            "value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheme: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    value: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    qualifier: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    preferred: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
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

    work_type: Mapped[str | None] = mapped_column(
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

    __table_args__ = (
        Index(
            "uq_nomens_entity_preferred_true",
            "entity_id",
            unique=True,
            postgresql_where=text("preferred = true"),
        ),
    )

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

class RelationPredicate(Base):
    __tablename__ = "relation_predicates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
class VocabularyScheme(Base):
    __tablename__ = "vocabulary_schemes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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
        default=uuid.uuid4,
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