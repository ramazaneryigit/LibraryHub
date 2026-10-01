"""Request bodies for field assertions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AssertionCreate(BaseModel):
    """A claim about one field of one record.

    `value` is deliberately untyped. What a field holds varies -- a title is a
    string, contributors are a list, a date is a date -- and forcing every claim
    through one shape would mean losing the shape before the reviewer sees it.
    """

    entity_id: UUID
    entity_type: str = Field(min_length=1, max_length=40)
    field: str = Field(min_length=1, max_length=120)
    value: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AssertionDecision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
