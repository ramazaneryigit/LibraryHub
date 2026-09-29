import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Entity,
    ReconciliationCandidate,
    ReconciliationDecision,
    SourceRecord,
)
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(
    prefix="/reconciliation",
    tags=["reconciliation"],
)


@router.get("/source-records/{source_record_id}")
def get_source_record_reconciliation(
    source_record_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    source_record = db.get(
        SourceRecord,
        source_record_id,
    )

    if source_record is None:
        raise HTTPException(
            status_code=404,
            detail="Source record not found",
        )

    candidates = db.scalars(
        select(ReconciliationCandidate)
        .where(
            ReconciliationCandidate.source_record_id
            == source_record_id
        )
        .order_by(
            ReconciliationCandidate.score.desc(),
            ReconciliationCandidate.created_at.asc(),
        )
    ).all()

    candidate_results = []

    for candidate in candidates:
        canonical_entity_id = resolve_canonical_entity_id(
            db=db,
            entity_id=candidate.candidate_entity_id,
        )

        entity = db.get(
            Entity,
            canonical_entity_id,
        )

        candidate_results.append(
            {
                "id": candidate.id,
                "candidate_entity_id": candidate.candidate_entity_id,
                "canonical_entity_id": canonical_entity_id,
                "entity_type": (
                    entity.entity_type
                    if entity is not None
                    else None
                ),
                "score": candidate.score,
                "method": candidate.method,
                "evidence": candidate.evidence,
                "created_at": candidate.created_at,
            }
        )

    decision = db.scalar(
        select(ReconciliationDecision).where(
            ReconciliationDecision.source_record_id
            == source_record_id
        )
    )

    decision_result = None

    if decision is not None:
        decision_result = {
            "id": decision.id,
            "candidate_id": decision.candidate_id,
            "status": decision.status,
            "origin": decision.origin,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "decision_method": decision.decision_method,
            "reviewed_by": decision.reviewed_by,
            "reviewed_at": decision.reviewed_at,
            "created_at": decision.created_at,
            "updated_at": decision.updated_at,
        }

    return {
        "source_record": {
            "id": source_record.id,
            "source_system": source_record.source_system,
            "source_record_id": source_record.source_record_id,
            "source_uri": source_record.source_uri,
            "record_type": source_record.record_type,
            "institution_entity_id": (
                source_record.institution_entity_id
            ),
            "retrieved_at": source_record.retrieved_at,
            "source_updated_at": source_record.source_updated_at,
            "content_hash": source_record.content_hash,
            "created_at": source_record.created_at,
        },
        "candidates": candidate_results,
        "decision": decision_result,
    }