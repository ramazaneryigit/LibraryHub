"""Request models for concepts."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["ConceptCreate"]


class ConceptCreate(BaseModel):
    preferred_label: str = Field(min_length=1, max_length=500)
    definition: str | None = None
    scheme: str | None = Field(default=None, max_length=100)
