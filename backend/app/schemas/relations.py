"""Request models for relations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["EntityRelationCreate"]


class EntityRelationCreate(BaseModel):
    object_entity_id: UUID
    predicate: str = Field(min_length=1, max_length=100)
