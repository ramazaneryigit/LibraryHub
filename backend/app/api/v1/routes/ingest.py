"""Loading a MARC file.

Takes the raw body rather than a multipart form, so there is no dependency to
install and `curl --data-binary @file.mrc` is the whole client. A catalogue import
is a file, and the file is the request.

Administrator-only, and through the owner credential: a batch belongs to one
library but writes rows for many, across two planes, so a tenant session could not
do it by construction.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from sqlalchemy.orm import Session

from ....db.models import User
from ...deps import owner_db, require_role
from ....services import marc_ingest


router = APIRouter(prefix="/ingest", tags=["ingestion"])
# A national catalogue export is hundreds of megabytes. This is a guard against a
# request that was never going to succeed, not a policy about file size.
MAX_BYTES = 256 * 1024 * 1024


@router.get("/batches")
def batches(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """Every import run, newest first.

    The report body is left out here and fetched per batch: a list is for
    choosing, a report is for reading.
    """

    rows = marc_ingest.list_batches(db, limit=limit)

    return {
        "count": len(rows),
        "batches": [
            {
                "id": str(row["id"]),
                "source_system": row["source_system"],
                "status": row["status"],
                "total": row["total"],
                "created": row["created"],
                "unchanged": row["unchanged"],
                "failed": row["failed"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
            }
            for row in rows
        ],
    }


@router.get("/batches/{batch_id}")
def batch(batch_id: str, db: Session = Depends(owner_db), user: User = Depends(require_role("admin"))):
    """One run, with what it could not read and why."""

    row = marc_ingest.read_batch(db, batch_id)

    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Batch not found",
        )

    report = row["report"]

    # psycopg hands JSONB back as a dict; a driver without a JSON type hands back
    # the text. Both are the same report and the client should not have to know
    # which database is underneath.
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except (TypeError, ValueError):
            report = None

    return {
        "id": str(row["id"]),
        "source_system": row["source_system"],
        "status": row["status"],
        "total": row["total"],
        "created": row["created"],
        "unchanged": row["unchanged"],
        "failed": row["failed"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "report": report,
    }


@router.post("/marc", status_code=http_status.HTTP_201_CREATED)
async def load_marc(
    request: Request,
    source: str = Query(min_length=1, max_length=100),
    name: str = Query(min_length=1, max_length=200),
    limit: int | None = Query(default=None, ge=1, le=1_000_000),
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """Read a MARC file and write what it says.

    `limit` exists so the first run against a real collection can be a hundred
    records rather than half a million. Walking up is how a mapping mistake is
    found before it has been applied fifty thousand times.
    """

    data = await request.body()

    if not data:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Body is empty: send the MARC file as the request body",
        )

    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{len(data)} bytes exceeds the {MAX_BYTES} byte limit",
        )

    report = marc_ingest.ingest(
        db,
        data,
        source_code=f"marc:{source}",
        source_name=name,
        limit=limit,
    )

    db.commit()

    return report
