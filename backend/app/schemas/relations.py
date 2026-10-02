"""Request models for relations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["EntityRelationCreate", "EntityRelationQualifierCreate", "EntityRelationQualifierResponse"]


class EntityRelationCreate(BaseModel):
    object_entity_id: UUID
    predicate: str = Field(min_length=1, max_length=100)


class EntityRelationQualifierCreate(BaseModel):
    """Makale nitelemesi oluşturma — cilt, sayı, sayfa, yıl."""

    entity_relation_id: UUID
    volume: str | None = Field(None, max_length=100)
    issue: str | None = Field(None, max_length=100)
    pages: str | None = Field(None, max_length=100)
    year: int | None = Field(None, ge=1000, le=2100)
    article_number: str | None = Field(None, max_length=100)
    doi: str | None = Field(None, max_length=200)


class EntityRelationQualifierResponse(BaseModel):
    """Makale nitelemesi yanıtı."""

    id: UUID
    entity_relation_id: UUID
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    year: int | None = None
    article_number: str | None = None
    doi: str | None = None

    model_config = {"from_attributes": True}
