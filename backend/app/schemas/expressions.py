"""Request models for expressions."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["ExpressionCreate"]


class ExpressionCreate(BaseModel):
    work_entity_id: UUID
    language: str | None = Field(default=None, max_length=100)
    expression_form: str | None = Field(default=None, max_length=100)
    description: str | None = None
