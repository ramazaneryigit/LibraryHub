import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import (
    Entity,
    ReconciliationCandidate,
    ReconciliationDecision,
    SourceRecord,
    Work,
)
from ....services.entity_merge import EntityMergeCycleError, resolve_canonical_entity_id
from ....services.reconciliation_freshness import check_freshness
from ....services.reconciliation_snapshot import capture_decision_snapshot
from ....services.reconciliation import generate_work_candidates
from ....services.reconciliation_policy import evaluate_work_reconciliation

class ReconciliationDecisionCreate(BaseModel):
    candidate_id: uuid.UUID | None = None

    status: str = Field(
        pattern="^(accepted|rejected|unresolved|new_entity)$",
    )

    origin: str = Field(
        default="manual",
        pattern="^(manual|automatic)$",
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    reason: str | None = None

    decision_method: str | None = Field(
        default=None,
        max_length=100,
    )

    reviewed_by: str | None = Field(
        default=None,
        max_length=200,
    )

router = APIRouter(
    prefix="/reconciliation",
    tags=["reconciliation"],
)


@router.get("/source-records/{source_record_id}/evaluation")
def evaluate_reconciliation(
    source_record_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    source_record = db.get(SourceRecord, source_record_id)
    if source_record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    if source_record.record_type != "work":
        raise HTTPException(status_code=400, detail="Policy evaluation supports only work records")
    return evaluate_work_reconciliation(db, source_record)


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
            "evidence_snapshot": decision.evidence_snapshot,
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

@router.post("/source-records/{source_record_id}/decision", status_code=201)
def create_reconciliation_decision(
    source_record_id: uuid.UUID,
    payload: ReconciliationDecisionCreate,
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

    existing = db.scalar(
        select(ReconciliationDecision).where(
            ReconciliationDecision.source_record_id
            == source_record_id
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Reconciliation decision already exists",
        )

    candidate = None

    if payload.candidate_id is not None:
        candidate = db.get(
            ReconciliationCandidate,
            payload.candidate_id,
        )

        if candidate is None:
            raise HTTPException(
                status_code=404,
                detail="Reconciliation candidate not found",
            )

        if candidate.source_record_id != source_record_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Reconciliation candidate does not belong "
                    "to this source record"
                ),
            )

    if payload.status == "accepted" and candidate is None:
        raise HTTPException(
            status_code=400,
            detail="Accepted decision requires a candidate",
        )

    if payload.status == "new_entity" and candidate is not None:
        raise HTTPException(
            status_code=400,
            detail="New entity decision must not have a candidate",
        )

    if payload.status == "accepted":
        if payload.origin == "automatic":
            raise HTTPException(status_code=409, detail={
                "code": "automatic_acceptance_not_calibrated",
                "message": "Automatic acceptance is disabled; manual review is required",
            })
        if source_record.record_type != "work":
            raise HTTPException(status_code=400, detail={
                "code": "acceptance_record_type_unsupported",
                "message": "Acceptance validation currently supports only work records",
            })
        try:
            canonical_id = resolve_canonical_entity_id(db, candidate.candidate_entity_id)
        except EntityMergeCycleError:
            raise HTTPException(status_code=409, detail={
                "code": "canonical_cycle",
                "message": "Canonical identity must be repaired before acceptance",
            })
        work = db.get(Work, canonical_id)
        if work is None:
            raise HTTPException(status_code=409, detail={
                "code": "canonical_work_missing",
                "message": "Candidate must resolve to an existing Work",
            })
        freshness = check_freshness(source_record, work, candidate)
        if freshness["status"] != "fresh":
            raise HTTPException(status_code=409, detail={
                "code": "candidate_evidence_requires_regeneration",
                "message": "Regenerate candidate evidence and review it before acceptance",
                "freshness": freshness,
            })

    decision = ReconciliationDecision(
        source_record_id=source_record_id,
        candidate_id=(
            candidate.id
            if candidate is not None
            else None
        ),
        status=payload.status,
        origin=payload.origin,
        confidence=payload.confidence,
        reason=payload.reason,
        decision_method=payload.decision_method,
        reviewed_by=payload.reviewed_by,
        reviewed_at=(
            datetime.now(timezone.utc)
            if payload.origin == "manual"
            else None
        ),
    )

    decision.evidence_snapshot = capture_decision_snapshot(db, source_record, candidate, decision)
    db.add(decision)
    db.commit()
    db.refresh(decision)

    return {
        "id": decision.id,
        "source_record_id": decision.source_record_id,
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
        "evidence_snapshot": decision.evidence_snapshot,
    }

@router.post(
    "/source-records/{source_record_id}/generate-candidates"
)
def generate_reconciliation_candidates(
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

    if source_record.record_type != "work":
        raise HTTPException(
            status_code=400,
            detail=(
                "Automatic candidate generation currently "
                "supports only work records"
            ),
        )

    candidates = generate_work_candidates(
        db=db,
        source_record=source_record,
    )

    return {
        "source_record_id": source_record.id,
        "candidate_count": len(candidates),
        "candidates": [
            {
                "id": candidate.id,
                "candidate_entity_id": (
                    candidate.candidate_entity_id
                ),
                "score": candidate.score,
                "method": candidate.method,
                "evidence": candidate.evidence,
            }
            for candidate in candidates
        ],
    }
