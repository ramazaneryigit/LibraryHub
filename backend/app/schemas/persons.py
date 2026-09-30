"""Request models for persons."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["PersonCreate", "NomenCreate"]


class PersonCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    given_name: str | None = Field(default=None, max_length=250)
    family_name: str | None = Field(default=None, max_length=250)
    biography: str | None = None


class NomenCreate(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=100)
    script: str | None = Field(default=None, max_length=50)
    nomen_type: str | None = Field(default=None, max_length=100)
    preferred: bool = False
