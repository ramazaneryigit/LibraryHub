"""Read-only Work policy preview. Scores are ranking signals, not probabilities."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ReconciliationCandidate, ReconciliationDecision, SourceRecord, Work
from .entity_merge import EntityMergeCycleError, resolve_canonical_entity_id

POLICY_VERSION = "work_review_v2"


def evaluate_work_reconciliation(db: Session, source: SourceRecord) -> dict:
    """Rank stored evidence without regenerating candidates or writing decisions.

    Keep the highest-scoring historical candidate as each canonical group's
    representative. Never add scores together or silently rewrite its evidence.
    Automatic eligibility stays disabled until calibration and evidence
    versioning are available.
    """
    candidates = db.scalars(select(ReconciliationCandidate).where(
        ReconciliationCandidate.source_record_id == source.id
    )).all()
    decision = db.scalar(select(ReconciliationDecision).where(
        ReconciliationDecision.source_record_id == source.id
    ))
    groups = {}
    excluded = []
    for candidate in sorted(candidates, key=lambda c: (-c.score, str(c.id))):
        try:
            canonical_id = resolve_canonical_entity_id(db, candidate.candidate_entity_id)
        except EntityMergeCycleError:
            excluded.append({"candidate_id": candidate.id, "reason": "canonical_cycle"})
            continue
        if db.get(Work, canonical_id) is None:
            excluded.append({"candidate_id": candidate.id, "reason": "canonical_work_missing"})
            continue
        member = {
            "candidate_id": candidate.id,
            "candidate_entity_id": candidate.candidate_entity_id,
            "score": candidate.score,
            "method": candidate.method,
            "evidence": candidate.evidence,
        }
        if canonical_id not in groups:
            groups[canonical_id] = {
                "canonical_entity_id": canonical_id,
                "representative_candidate_id": candidate.id,
                "score": candidate.score,
                "members": [],
            }
        groups[canonical_id]["members"].append(member)

    ranking = sorted(groups.values(), key=lambda g: (-g["score"], str(g["canonical_entity_id"])))
    for rank, group in enumerate(ranking, 1):
        group["rank"] = rank
    top = ranking[0] if ranking else None
    second = ranking[1] if len(ranking) > 1 else None
    margin = round(top["score"] - second["score"], 8) if second else None
    reasons = ["automatic_acceptance_not_calibrated", "candidate_freshness_not_verified"]
    if not ranking:
        reasons.append("no_usable_candidates")
    elif second is None:
        reasons.append("no_second_distinct_candidate")
    elif margin == 0:
        reasons.append("top_score_tie")
    if top:
        evidence = top["members"][0]["evidence"]
        comparisons = evidence.get("field_comparisons") if isinstance(evidence, dict) else None
        if not isinstance(comparisons, dict):
            reasons.append("field_comparison_unavailable")
        else:
            for field in ("language", "work_type"):
                comparison = comparisons.get(field)
                status = comparison.get("status") if isinstance(comparison, dict) else None
                if status in ("conflict", "missing_source", "missing_candidate", "missing_both", "invalid_value"):
                    reasons.append(f"top_candidate_{field}_{status}")
                elif status != "match":
                    reasons.append(f"top_candidate_{field}_comparison_unavailable")
    if excluded:
        reasons.append("invalid_canonical_candidates")
    if len(candidates) - len(excluded) > len(ranking):
        reasons.append("canonical_duplicates_grouped")
    if decision is not None:
        reasons.append("existing_decision_preserved")

    raw = source.raw_data if isinstance(source.raw_data, dict) else {}
    missing_fields = [key for key in ("title", "language", "work_type")
                      if not isinstance(raw.get(key), str) or not raw[key].strip()]
    if missing_fields:
        reasons.append("missing_source_fields")
    return {
        "source_record_id": source.id,
        "policy_version": POLICY_VERSION,
        "mode": "preview",
        "recommendation": "manual_review" if ranking else "unresolved",
        "automatic_acceptance_eligible": False,
        "reason_codes": reasons,
        "missing_source_fields": missing_fields,
        "candidate_count": len(candidates),
        "distinct_candidate_count": len(ranking),
        "top_candidate": top,
        "second_candidate": second,
        "score_margin": margin,
        "ranking": ranking,
        "excluded_candidates": excluded,
        "current_decision": None if decision is None else {
            "id": decision.id, "candidate_id": decision.candidate_id,
            "status": decision.status, "origin": decision.origin,
        },
    }
