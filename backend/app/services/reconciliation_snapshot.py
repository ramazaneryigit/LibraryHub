"""Detached evidence copies captured when a decision is first recorded."""

from copy import deepcopy
from datetime import datetime, timezone

from ..models import Work
from .entity_merge import EntityMergeCycleError, resolve_canonical_entity_id
from .reconciliation_freshness import check_freshness


def capture_decision_snapshot(db, source, candidate, decision) -> dict:
    snapshot = {
        "snapshot_version": "decision_evidence_v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "id": str(source.id),
            "source_system": source.source_system,
            "source_record_id": source.source_record_id,
            "source_uri": source.source_uri,
            "record_type": source.record_type,
            "raw_data": deepcopy(source.raw_data),
            "content_hash": source.content_hash,
        },
        "decision": {
            "status": decision.status, "origin": decision.origin,
            "confidence": decision.confidence, "reason": decision.reason,
            "decision_method": decision.decision_method,
            "reviewed_by": decision.reviewed_by,
        },
        "candidate": None,
    }
    if candidate is None:
        return snapshot
    canonical_id = None
    work = None
    try:
        canonical_id = resolve_canonical_entity_id(db, candidate.candidate_entity_id)
        work = db.get(Work, canonical_id)
        freshness = check_freshness(source, work, candidate) if work else {
            "status": "unknown", "reason_codes": ["canonical_work_missing"]}
    except EntityMergeCycleError:
        freshness = {"status": "unknown", "reason_codes": ["canonical_cycle"]}
    snapshot["candidate"] = {
        "id": str(candidate.id),
        "candidate_entity_id": str(candidate.candidate_entity_id),
        "canonical_entity_id": str(canonical_id) if canonical_id else None,
        "score": candidate.score,
        "method": candidate.method,
        "evidence": deepcopy(candidate.evidence),
        "freshness_at_decision": freshness,
        "canonical_work_at_decision": None if work is None else {
            "entity_id": str(work.entity_id), "canonical_title": work.canonical_title,
            "original_language": work.original_language, "work_type": work.work_type,
        },
    }
    return snapshot
