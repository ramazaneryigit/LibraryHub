"""Request models for works."""

from __future__ import annotations

from pydantic import BaseModel


__all__ = ["WorkCreate"]


class WorkCreate(BaseModel):
    canonical_title: str
    original_title: str | None = None
    original_language: str | None = None
    work_type: str | None = None
    description: str | None = None
