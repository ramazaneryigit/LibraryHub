from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.ingestion import (
    ingest_source_records,
)


router = APIRouter(
    prefix="/ingestion",
    tags=["ingestion"],
)


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


@router.post("/source-records")
def ingest_records(
    payload: IngestionRequest,
    db: Session = Depends(get_db),
):
    records = [
        record.model_dump()
        for record in payload.records
    ]

    return ingest_source_records(
        db=db,
        source_system=payload.source_system,
        records=records,
    )