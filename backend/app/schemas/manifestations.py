"""Request models for manifestations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["ManifestationCreate"]


class ManifestationCreate(BaseModel):
    expression_entity_id: UUID
    publication_statement: str | None = Field(default=None, max_length=1000)
    publication_date: str | None = Field(default=None, max_length=100)
    edition_statement: str | None = Field(default=None, max_length=500)
    carrier_type: str | None = Field(default=None, max_length=100)
    extent: str | None = Field(default=None, max_length=500)
    notes: str | None = None
