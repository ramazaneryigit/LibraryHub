import uuid
from pathlib import Path
import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Entity, SourceRecord, Work
from app.services.reconciliation import (
    evaluate_decision_policy,
    generate_work_candidates,
)


CONTROLLED_DESCRIPTION = (
    "Controlled reconciliation policy fixture. "
    "Not bibliographic production data."
)

WORK_FIXTURES = [
    {
        "entity_id": uuid.UUID(
            "3f2a9c1e-6b14-4d2a-9c8f-1e0a7b4d2c11"
        ),
        "canonical_title": "Ambervolt Close Fixture Title",
        "original_language": "tr",
        "work_type": "textbook",
    },
    {
        "entity_id": uuid.UUID(
            "3f2a9c1e-6b14-4d2a-9c8f-1e0a7b4d2c12"
        ),
        "canonical_title": "Ambervolt Close Fixture Titel",
        "original_language": "tr",
        "work_type": "textbook",
    },
    {
        "entity_id": uuid.UUID(
            "8c4d21aa-91f0-4b33-8d7e-2a6f0c91b201"
        ),
        "canonical_title": "Cobaltstrong Unique Workname",
        "original_language": "tr",
        "work_type": "textbook",
    },
    {
        "entity_id": uuid.UUID(
            "8c4d21aa-91f0-4b33-8d7e-2a6f0c91b202"
        ),
        "canonical_title": "Cobaltstrong Distant Work",
        "original_language": "tr",
        "work_type": "textbook",
    },
]

SOURCE_FIXTURES = [
    {
        "id": uuid.UUID(
            "c0a5e001-24f2-4870-ba1b-c04dcae1de01"
        ),
        "source_system": "libraryhub-test",
        "source_record_id": "RECON-POLICY-CLOSE-001",
        "raw_data": {
            "title": "Ambervolt Close Fixture Title",
            "language": "tr",
            "work_type": "textbook",
        },
    },
    {
        "id": uuid.UUID(
            "c0a5e001-24f2-4870-ba1b-c04dcae1de02"
        ),
        "source_system": "libraryhub-test",
        "source_record_id": "RECON-POLICY-STRONG-001",
        "raw_data": {
            "title": "Cobaltstrong Unique Workname",
            "language": "tr",
            "work_type": "textbook",
        },
    },
]


def ensure_work(db, fixture):
    existing_by_id = db.get(
        Work,
        fixture["entity_id"],
    )

    if existing_by_id is not None:
        return existing_by_id

    existing_by_title = db.scalar(
        select(Work).where(
            Work.canonical_title
            == fixture["canonical_title"]
        )
    )

    if existing_by_title is not None:
        return existing_by_title

    entity = Entity(
        id=fixture["entity_id"],
        entity_type="WORK",
    )

    work = Work(
        entity_id=fixture["entity_id"],
        canonical_title=fixture["canonical_title"],
        original_language=fixture[
            "original_language"
        ],
        work_type=fixture["work_type"],
        description=CONTROLLED_DESCRIPTION,
    )

    db.add(entity)
    db.add(work)
    db.flush()

    return work


def ensure_source_record(db, fixture):
    existing = db.scalar(
        select(SourceRecord).where(
            SourceRecord.source_system
            == fixture["source_system"],
            SourceRecord.source_record_id
            == fixture["source_record_id"],
        )
    )

    if existing is not None:
        return existing

    source_record = SourceRecord(
        id=fixture["id"],
        source_system=fixture["source_system"],
        source_record_id=fixture[
            "source_record_id"
        ],
        record_type="work",
        raw_data=fixture["raw_data"],
    )

    db.add(source_record)
    db.flush()

    return source_record


def main():
    db = SessionLocal()

    try:
        works = [
            ensure_work(db, fixture)
            for fixture in WORK_FIXTURES
        ]

        source_records = [
            ensure_source_record(db, fixture)
            for fixture in SOURCE_FIXTURES
        ]

        db.commit()

        print("Controlled policy fixture works:")

        for work in works:
            print(
                f"  {work.entity_id}  {work.canonical_title}"
            )

        print("Controlled policy source records:")

        for source_record in source_records:
            candidates = generate_work_candidates(
                db=db,
                source_record=source_record,
            )
            policy = evaluate_decision_policy(
                candidates
            )

            print(
                f"  {source_record.source_record_id}  {source_record.id}"
            )
            print(
                "    candidate_count="
                f"{policy['candidate_count']}"
            )
            print(
                "    score_margin="
                f"{policy['score_margin']}"
            )
            print(
                "    recommendation="
                f"{policy['recommendation']}"
            )
            print(
                "    automatic_acceptance_eligible="
                f"{policy['automatic_acceptance_eligible']}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
