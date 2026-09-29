import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SourceRecord


def calculate_content_hash(raw_data) -> str:
    serialized = json.dumps(
        raw_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def ingest_source_records(
    db: Session,
    source_system: str,
    records: list[dict],
) -> dict:
    result = {
        "total": len(records),
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc)

    # Geçerli source_record_id değerlerini önceden topla.
    source_record_ids = [
        str(record.get("source_record_id"))
        for record in records
        if record.get("source_record_id")
    ]

    # Batch içindeki mevcut kayıtları tek sorguda getir.
    existing_records = db.scalars(
        select(SourceRecord).where(
            SourceRecord.source_system == source_system,
            SourceRecord.source_record_id.in_(source_record_ids),
        )
    ).all()

    existing_by_id = {
        record.source_record_id: record
        for record in existing_records
    }

    for index, record in enumerate(records):
        try:
            source_record_id = record.get("source_record_id")
            record_type = record.get("record_type")

            if not source_record_id:
                raise ValueError(
                    "source_record_id is required"
                )

            if not record_type:
                raise ValueError(
                    "record_type is required"
                )

            source_record_id = str(source_record_id)

            raw_data = record.get("raw_data")
            if raw_data is None:
                raw_data = {}

            content_hash = calculate_content_hash(
                raw_data
            )

            existing = existing_by_id.get(
                source_record_id
            )

            if existing is None:
                source_record = SourceRecord(
                    source_system=source_system,
                    source_record_id=source_record_id,
                    source_uri=record.get(
                        "source_uri"
                    ),
                    record_type=str(record_type),
                    institution_entity_id=record.get(
                        "institution_entity_id"
                    ),
                    retrieved_at=now,
                    source_updated_at=record.get(
                        "source_updated_at"
                    ),
                    raw_data=raw_data,
                    content_hash=content_hash,
                )

                db.add(source_record)

                # Aynı batch içinde aynı ID tekrar gelirse
                # ikinci kez INSERT edilmeye çalışılmasını önle.
                existing_by_id[
                    source_record_id
                ] = source_record

                result["created"] += 1
                continue

            metadata_changed = (
                existing.source_uri
                != record.get("source_uri")
                or existing.record_type
                != str(record_type)
                or str(
                    existing.institution_entity_id
                )
                != str(
                    record.get(
                        "institution_entity_id"
                    )
                )
            )

            content_changed = (
                existing.content_hash
                != content_hash
            )

            if (
                not metadata_changed
                and not content_changed
            ):
                result["unchanged"] += 1
                continue

            existing.source_uri = record.get(
                "source_uri"
            )
            existing.record_type = str(
                record_type
            )
            existing.institution_entity_id = (
                record.get(
                    "institution_entity_id"
                )
            )
            existing.retrieved_at = now
            existing.source_updated_at = (
                record.get(
                    "source_updated_at"
                )
            )
            existing.raw_data = raw_data
            existing.content_hash = content_hash

            result["updated"] += 1

        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(
                {
                    "index": index,
                    "source_record_id": (
                        record.get(
                            "source_record_id"
                        )
                    ),
                    "error": str(exc),
                }
            )

    db.commit()

    return result
    
def ingest_jsonl_stream(
    db: Session,
    source_system: str,
    stream,
    batch_size: int = 500,
) -> dict:
    if batch_size < 1:
        raise ValueError(
            "batch_size must be greater than zero"
        )

    result = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
        "errors": [],
        "batches": 0,
    }

    batch = []

    def process_batch():
        if not batch:
            return

        batch_result = ingest_source_records(
            db=db,
            source_system=source_system,
            records=batch,
        )

        result["created"] += batch_result["created"]
        result["updated"] += batch_result["updated"]
        result["unchanged"] += batch_result["unchanged"]
        result["failed"] += batch_result["failed"]

        result["errors"].extend(
            batch_result["errors"]
        )

        result["batches"] += 1

        batch.clear()

    for line_number, raw_line in enumerate(
        stream,
        start=1,
    ):
        result["total"] += 1

        try:
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode(
                    "utf-8"
                )

            line = raw_line.strip()

            if not line:
                result["total"] -= 1
                continue

            record = json.loads(line)

            if not isinstance(record, dict):
                raise ValueError(
                    "JSONL line must contain an object"
                )

            batch.append(record)

            if len(batch) >= batch_size:
                process_batch()

        except Exception as exc:
            result["failed"] += 1

            result["errors"].append(
                {
                    "line": line_number,
                    "error": str(exc),
                }
            )

    process_batch()

    return result