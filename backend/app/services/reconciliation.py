import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session
from difflib import SequenceMatcher

from ..models import (
    ReconciliationCandidate,
    SourceRecord,
    Work,
)
from .entity_merge import resolve_canonical_entity_id
from .reconciliation_freshness import METHOD, capture_inputs


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


def generate_work_candidates(
    db: Session,
    source_record: SourceRecord,
) -> list[ReconciliationCandidate]:
    raw_data = source_record.raw_data

    if not isinstance(raw_data, dict):
        return []

    source_title = normalize_text(
        raw_data.get("title")
    )
    if source_title is None:
        return []

    works = db.scalars(
        select(Work)
    ).all()

    generated_candidates = []
    seen_canonical_entity_ids = set()

    for work in works:
        work_title = normalize_text(
            work.canonical_title
        )

        if work_title is None:
            continue

        title_similarity = SequenceMatcher(
            None,
            source_title,
            work_title,
        ).ratio()

        # İlk fuzzy sürümde çok zayıf başlıkları aday yapmıyoruz.
        if title_similarity < 0.70:
            continue

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

        # Redirect sonrasında gerçek canonical Work başlığıyla
        # benzerliği yeniden hesapla.
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
        evidence["input_fingerprints"] = capture_inputs(source_record, canonical_work)
        evidence["field_comparisons"] = {
            "language": compare_field(raw_data.get("language"), canonical_work.original_language),
            "work_type": compare_field(raw_data.get("work_type"), canonical_work.work_type),
        }
        for field, comparison in evidence["field_comparisons"].items():
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
            existing_candidate.method = (
                METHOD
            )
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