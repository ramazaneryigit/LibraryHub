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
    source_language = normalize_text(
        raw_data.get("language")
    )
    source_work_type = normalize_text(
        raw_data.get("work_type")
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

        canonical_language = normalize_text(
            canonical_work.original_language
        )

        if (
            source_language is not None
            and canonical_language is not None
            and source_language == canonical_language
        ):
            score += 0.15
            evidence["language_match"] = True
            evidence["language_score"] = 0.15

        canonical_work_type = normalize_text(
            canonical_work.work_type
        )

        if (
            source_work_type is not None
            and canonical_work_type is not None
            and source_work_type == canonical_work_type
        ):
            score += 0.15
            evidence["work_type_match"] = True
            evidence["work_type_score"] = 0.15

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
                "work_fuzzy_title_v2"
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
            method="work_fuzzy_title_v2",
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