"""Request models for ingestion."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


__all__ = ["IngestionRecord", "IngestionRequest"]


class IngestionRecord(BaseModel):
    source_record_id: str
    record_type: str
    source_uri: str | None = None
    institution_entity_id: str | None = None
    source_updated_at: str | None = None
    raw_data: dict[str, Any] = Field(
        default_factory=dict
    )


class IngestionRequest(BaseModel):
    source_system: str
    records: list[IngestionRecord]
