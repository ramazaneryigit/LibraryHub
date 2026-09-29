"""Read-only Work policy preview. Scores are ranking signals, not probabilities."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ReconciliationCandidate, ReconciliationDecision, SourceRecord, Work
from .entity_merge import EntityMergeCycleError, resolve_canonical_entity_id
from .reconciliation_freshness import check_freshness

POLICY_VERSION = "work_review_v3"


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
        canonical_work = db.get(Work, canonical_id)
        if canonical_work is None:
            excluded.append({"candidate_id": candidate.id, "reason": "canonical_work_missing"})
            continue
        member = {
            "candidate_id": candidate.id,
            "candidate_entity_id": candidate.candidate_entity_id,
            "score": candidate.score,
            "method": candidate.method,
            "evidence": candidate.evidence,
            "freshness": check_freshness(source, canonical_work, candidate),
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
    freshness_counts = {"fresh": 0, "stale": 0, "unknown": 0}
    for group in ranking:
        group["freshness"] = group["members"][0]["freshness"]
        for member in group["members"]:
            freshness_counts[member["freshness"]["status"]] += 1
    reasons = ["automatic_acceptance_not_calibrated"]
    if freshness_counts["stale"]:
        reasons.append("candidate_evidence_stale")
    if freshness_counts["unknown"]:
        reasons.append("candidate_freshness_not_verified")
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
        "freshness_counts": freshness_counts,
        "requires_candidate_regeneration": bool(
            freshness_counts["stale"] or freshness_counts["unknown"]
        ),
        "stored_candidate_inputs_current": bool(ranking) and not excluded and not (
            freshness_counts["stale"] or freshness_counts["unknown"]
        ),
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
            "evidence_snapshot": decision.evidence_snapshot,
        },
    }
