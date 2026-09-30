from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ...deps import require_admin
from ....db import get_db
from ....services.ingestion import (
    ingest_jsonl_job,
    ingest_source_records,
)
from ....schemas.ingestion import IngestionRecord, IngestionRequest


router = APIRouter(
    prefix="/ingestion",
    tags=["ingestion"],
)


@router.post("/source-records", dependencies=[Depends(require_admin)])
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
    
@router.post("/jsonl", dependencies=[Depends(require_admin)])
def ingest_jsonl_file(
    source_system: str = Form(...),
    batch_size: int = Form(500),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if batch_size < 1 or batch_size > 10000:
        raise HTTPException(
            status_code=400,
            detail="batch_size must be between 1 and 10000",
        )

    filename = file.filename or ""

    if not filename.lower().endswith(".jsonl"):
        raise HTTPException(
            status_code=400,
            detail="Only .jsonl files are supported",
        )

    try:
        return ingest_jsonl_job(
            db=db,
            source_system=source_system,
            stream=file.file,
            batch_size=batch_size,
        )
    finally:
        file.file.close()