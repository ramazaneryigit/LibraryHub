import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from difflib import SequenceMatcher

from ..models import (
    ReconciliationCandidate,
    SourceRecord,
    Work,
)
from .entity_merge import resolve_canonical_entity_id
from .reconciliation_freshness import METHOD, capture_inputs


# Evaluation-only bands for ranking interpretation.
# These are not production automatic-acceptance thresholds
# and must not persist ReconciliationDecision rows.
DECISION_POLICY_VERSION = "decision_policy_v1_eval"

EVALUATION_AMBIGUOUS_MARGIN_BELOW = 0.05
EVALUATION_STRONG_MARGIN_AT_LEAST = 0.15
EVALUATION_STRONG_TOP_SCORE_AT_LEAST = 0.90
EVALUATION_WEAK_TOP_SCORE_BELOW = 0.75


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    normalized = re.sub(
        r"[^\w\s]",
        " ",
        normalized,
        flags=re.UNICODE,
    )

    normalized = " ".join(
        normalized.split()
    )

    return normalized or None


def compare_field(source_value, candidate_value) -> dict:
    """Compare controlled text values without confusing absence with conflict."""
    def classify(value):
        if value is not None and not isinstance(value, str):
            return None, "invalid"
        normalized = normalize_text(value)
        return normalized, "missing" if normalized is None else "present"

    source_normalized, source_state = classify(source_value)
    candidate_normalized, candidate_state = classify(candidate_value)
    if "invalid" in (source_state, candidate_state):
        status = "invalid_value"
    elif source_state == candidate_state == "missing":
        status = "missing_both"
    elif source_state == "missing":
        status = "missing_source"
    elif candidate_state == "missing":
        status = "missing_candidate"
    else:
        status = "match" if source_normalized == candidate_normalized else "conflict"
    return {
        "status": status,
        "source_value": source_value,
        "candidate_value": candidate_value,
        "source_normalized": source_normalized,
        "candidate_normalized": candidate_normalized,
        "source_state": source_state,
        "candidate_state": candidate_state,
    }

WORK_RETRIEVAL_LIMIT = 100
WORK_TRIGRAM_THRESHOLD = 0.30


def retrieve_work_candidates(
    db: Session,
    source_title: str,
) -> list[Work]:
    similarity = func.similarity(
        func.lower(Work.canonical_title),
        source_title,
    )

    return db.scalars(
        select(Work)
        .where(
            Work.canonical_title.is_not(None),
            similarity >= WORK_TRIGRAM_THRESHOLD,
        )
        .order_by(
            similarity.desc(),
            Work.entity_id,
        )
        .limit(WORK_RETRIEVAL_LIMIT)
    ).all()

def generate_work_candidates(
    db: Session,
    source_record: SourceRecord,
) -> list[ReconciliationCandidate]:
    raw_data = source_record.raw_data

    if not isinstance(raw_data, dict):
        return []

    raw_source_title = raw_data.get("title")
    source_title = normalize_text(raw_source_title)

    if source_title is None:
        return []

    # PostgreSQL pg_trgm yalnızca güçlü olabilecek küçük bir Work
    # havuzunu getirir. Böylece bütün works tablosu Python'a çekilmez.
        works = retrieve_work_candidates(
        db=db,
        source_title=source_title,
    )

    generated_candidates = []
    seen_canonical_entity_ids = set()

    for work in works:
        canonical_entity_id = resolve_canonical_entity_id(
            db=db,
            entity_id=work.entity_id,
        )

        if canonical_entity_id in seen_canonical_entity_ids:
            continue

        seen_canonical_entity_ids.add(
            canonical_entity_id
        )

        canonical_work = db.get(
            Work,
            canonical_entity_id,
        )

        if canonical_work is None:
            continue

        canonical_title = normalize_text(
            canonical_work.canonical_title
        )

        if canonical_title is None:
            continue

        # pg_trgm yalnızca retrieval katmanıdır.
        # Nihai başlık skoru mevcut Python algoritmasıyla hesaplanır.
        title_similarity = SequenceMatcher(
            None,
            source_title,
            canonical_title,
        ).ratio()

        if title_similarity < 0.70:
            continue

        title_score = title_similarity * 0.70
        score = title_score

        evidence = {
            "title_similarity": round(
                title_similarity,
                4,
            ),
            "title_score": round(
                title_score,
                4,
            ),
            "language_match": False,
            "language_score": 0.0,
            "work_type_match": False,
            "work_type_score": 0.0,
        }

        evidence["evidence_version"] = "work_fields_v2"
        evidence["input_fingerprints"] = capture_inputs(
            source_record,
            canonical_work,
        )
        evidence["field_comparisons"] = {
            "language": compare_field(
                raw_data.get("language"),
                canonical_work.original_language,
            ),
            "work_type": compare_field(
                raw_data.get("work_type"),
                canonical_work.work_type,
            ),
        }

        for field, comparison in evidence[
            "field_comparisons"
        ].items():
            if comparison["status"] == "match":
                score += 0.15
                evidence[f"{field}_match"] = True
                evidence[f"{field}_score"] = 0.15

        score = round(
            min(score, 1.0),
            4,
        )

        existing_candidate = db.scalar(
            select(ReconciliationCandidate).where(
                ReconciliationCandidate.source_record_id
                == source_record.id,
                ReconciliationCandidate.candidate_entity_id
                == canonical_entity_id,
            )
        )

        if existing_candidate is not None:
            existing_candidate.score = score
            existing_candidate.method = METHOD
            existing_candidate.evidence = evidence

            generated_candidates.append(
                existing_candidate
            )
            continue

        candidate = ReconciliationCandidate(
            source_record_id=source_record.id,
            candidate_entity_id=canonical_entity_id,
            score=score,
            method=METHOD,
            evidence=evidence,
        )

        db.add(candidate)
        generated_candidates.append(candidate)

    db.commit()

    for candidate in generated_candidates:
        db.refresh(candidate)

    generated_candidates.sort(
        key=lambda candidate: candidate.score,
        reverse=True,
    )

    return generated_candidates


def rank_reconciliation_candidates(candidates):
    return sorted(
        candidates,
        key=lambda candidate: (
            -float(candidate.score),
            str(getattr(candidate, "id", "")),
        ),
    )


def summarize_candidate_evidence(evidence):
    if not isinstance(evidence, dict):
        evidence = {}

    title_similarity = evidence.get(
        "title_similarity"
    )
    language_match = bool(
        evidence.get("language_match")
    )
    work_type_match = bool(
        evidence.get("work_type_match")
    )

    strength = "weak"

    if isinstance(title_similarity, (int, float)):
        if (
            title_similarity >= 0.95
            and (
                language_match
                or work_type_match
            )
        ):
            strength = "strong"
        elif title_similarity >= 0.85:
            strength = "moderate"

    supporting_signals = []

    if isinstance(title_similarity, (int, float)):
        supporting_signals.append("title")

    if language_match:
        supporting_signals.append("language")

    if work_type_match:
        supporting_signals.append("work_type")

    return {
        "label": strength,
        "title_similarity": title_similarity,
        "language_match": language_match,
        "work_type_match": work_type_match,
        "supporting_signals": supporting_signals,
    }


def _candidate_policy_summary(candidate, rank):
    evidence = candidate.evidence

    if not isinstance(evidence, dict):
        evidence = {}

    return {
        "rank": rank,
        "id": candidate.id,
        "candidate_entity_id": (
            candidate.candidate_entity_id
        ),
        "score": candidate.score,
        "method": candidate.method,
        "evidence": evidence,
        "evidence_strength": (
            summarize_candidate_evidence(
                evidence
            )
        ),
    }


def evaluate_decision_policy(candidates):
    ranked_candidates = rank_reconciliation_candidates(
        list(candidates)
    )

    ranked_summaries = [
        _candidate_policy_summary(
            candidate,
            rank=index + 1,
        )
        for index, candidate in enumerate(
            ranked_candidates
        )
    ]

    top_candidate = (
        ranked_summaries[0]
        if ranked_summaries
        else None
    )
    second_candidate = (
        ranked_summaries[1]
        if len(ranked_summaries) > 1
        else None
    )

    score_margin = None

    if (
        top_candidate is not None
        and second_candidate is not None
    ):
        score_margin = round(
            float(top_candidate["score"])
            - float(second_candidate["score"]),
            4,
        )

    reasons = []
    recommendation = "manual_review"
    automatic_acceptance_eligible = False

    if top_candidate is None:
        recommendation = "new_entity_review"
        reasons.append(
            "No candidates were generated"
        )
    elif second_candidate is None:
        recommendation = "manual_review"
        reasons.append(
            "Second candidate is absent, so uniqueness cannot be confirmed"
        )
        reasons.append(
            "A single high score is not treated as automatic acceptance"
        )
    else:
        top_score = float(top_candidate["score"])
        evidence_strength = top_candidate[
            "evidence_strength"
        ]["label"]

        if score_margin < EVALUATION_AMBIGUOUS_MARGIN_BELOW:
            recommendation = "manual_review"
            reasons.append(
                "Top and second candidate scores are too close"
            )
        elif top_score < EVALUATION_WEAK_TOP_SCORE_BELOW:
            recommendation = "new_entity_review"
            reasons.append(
                "Top candidate score is weak relative to evaluation bands"
            )
        elif (
            top_score
            >= EVALUATION_STRONG_TOP_SCORE_AT_LEAST
            and score_margin
            >= EVALUATION_STRONG_MARGIN_AT_LEAST
            and evidence_strength == "strong"
        ):
            recommendation = (
                "automatic_accept_eligible"
            )
            automatic_acceptance_eligible = True
            reasons.append(
                "Top candidate is clearly separated from the second candidate"
            )
            reasons.append(
                "Evidence strength is labeled strong for evaluation only"
            )
        else:
            recommendation = "manual_review"
            reasons.append(
                "Score margin or evidence is not strong enough for eligibility"
            )

    return {
        "policy_version": DECISION_POLICY_VERSION,
        "production_ready": False,
        "writes_automatic_decision": False,
        "evaluation_bands": {
            "ambiguous_margin_below": (
                EVALUATION_AMBIGUOUS_MARGIN_BELOW
            ),
            "strong_margin_at_least": (
                EVALUATION_STRONG_MARGIN_AT_LEAST
            ),
            "strong_top_score_at_least": (
                EVALUATION_STRONG_TOP_SCORE_AT_LEAST
            ),
            "weak_top_score_below": (
                EVALUATION_WEAK_TOP_SCORE_BELOW
            ),
        },
        "candidate_count": len(ranked_summaries),
        "ranked_candidates": ranked_summaries,
        "top_candidate": top_candidate,
        "second_candidate": second_candidate,
        "score_margin": score_margin,
        "automatic_acceptance_eligible": (
            automatic_acceptance_eligible
        ),
        "recommendation": recommendation,
        "reasons": reasons,
    }
