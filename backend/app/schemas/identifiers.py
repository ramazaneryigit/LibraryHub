"""Request models for identifiers."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["IdentifierCreate"]


class IdentifierCreate(BaseModel):
    scheme: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    qualifier: str | None = Field(default=None, max_length=500)
    preferred: bool = False
