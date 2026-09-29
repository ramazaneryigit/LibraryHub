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

    for index, record in enumerate(records):
        try:
            source_record_id = record.get(
                "source_record_id"
            )

            record_type = record.get(
                "record_type"
            )

            if not source_record_id:
                raise ValueError(
                    "source_record_id is required"
                )

            if not record_type:
                raise ValueError(
                    "record_type is required"
                )

            raw_data = record.get(
                "raw_data"
            )

            if raw_data is None:
                raw_data = {}

            content_hash = calculate_content_hash(
                raw_data
            )

            existing = db.scalar(
                select(SourceRecord).where(
                    SourceRecord.source_system
                    == source_system,
                    SourceRecord.source_record_id
                    == str(source_record_id),
                )
            )

            if existing is None:
                source_record = SourceRecord(
                    source_system=source_system,
                    source_record_id=str(
                        source_record_id
                    ),
                    source_uri=record.get(
                        "source_uri"
                    ),
                    record_type=str(
                        record_type
                    ),
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
            existing.content_hash = (
                content_hash
            )

            result["updated"] += 1

        except Exception as exc:
            result["failed"] += 1

            result["errors"].append(
                {
                    "index": index,
                    "source_record_id":
                        record.get(
                            "source_record_id"
                        ),
                    "error": str(exc),
                }
            )

    db.commit()

    return result