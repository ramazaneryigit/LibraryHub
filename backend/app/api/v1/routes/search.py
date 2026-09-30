from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import Concept
from ....services import search_index
from ....services.work_detail import build_work_detail
from ....services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["search"])


@router.get("/search/concept/{concept_entity_id}")
def search_by_concept(
    concept_entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_concept_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=concept_entity_id,
    )

    concept = db.get(
        Concept,
        canonical_concept_entity_id,
    )

    if concept is None:
        raise HTTPException(
            status_code=404,
            detail="Concept not found",
        )

    query = """
    WITH RECURSIVE concept_tree AS (
        SELECT
            c.entity_id,
            c.preferred_label,
            0 AS level
        FROM concepts c
        WHERE c.entity_id = :concept_id

        UNION ALL

        SELECT
            c.entity_id,
            c.preferred_label,
            ct.level + 1
        FROM concept_tree ct
        JOIN entity_relation er
          ON er.object_entity_id = ct.entity_id
         AND er.predicate = 'broader'
        JOIN concepts c
          ON c.entity_id = er.subject_entity_id
    )
    SELECT
        w.entity_id,
        w.canonical_title,
        ct.preferred_label AS matched_concept,
        ct.level
    FROM concept_tree ct
    JOIN entity_relation er
      ON er.object_entity_id = ct.entity_id
     AND er.predicate = 'has_subject'
    JOIN works w
      ON w.entity_id = er.subject_entity_id
    ORDER BY
        ct.level,
        w.canonical_title
    """

    rows = db.execute(
        text(query),
        {
            "concept_id": str(canonical_concept_entity_id),
        },
    ).mappings().all()

    results = []

    seen_work_ids = set()

    for row in rows:
        work_detail = build_work_detail(
            work_entity_id=row["entity_id"],
            db=db,
        )

        if work_detail is None:
            continue

        canonical_work_entity_id = work_detail["entity_id"]

        if canonical_work_entity_id in seen_work_ids:
            continue

        seen_work_ids.add(canonical_work_entity_id)

        results.append({
            "work_entity_id": canonical_work_entity_id,
            "canonical_title": work_detail["canonical_title"],
            "matched_concept": row["matched_concept"],
            "level": row["level"],
            "authors": work_detail["authors"],
            "expressions": work_detail["expressions"],
        })

    return {
        "concept": {
            "entity_id": str(canonical_concept_entity_id),
            "preferred_label": concept.preferred_label,
        },
        "results": results,
    }

@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # `min_length=1` lets a single space through, and the old code then built the
    # pattern '%%', which matches every row: a whitespace-only query answered
    # with fifty arbitrary works instead of saying the query was empty.
    if not q.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Search query must contain at least one "
                "non-whitespace character"
            ),
        )
    probe = q.strip()

    # Candidates come from the derived index, not from a twenty-condition join.
    #
    # That join walked works, agents, nomens, identifiers, subjects, expressions,
    # manifestations, publishers and copies in one statement and matched each
    # with its own `ILIKE` -- measured at 944 ms at the top of §15.2, and growing
    # with every field anybody thought to search.
    #
    # `search_documents` holds one normalized body per entity plus the works a
    # match on it resolves to, so an author-name match finds the person's document
    # and resolves to their works without this query naming the author at all.
    #
    # The index is not a new source of truth. It is built from these same tables,
    # `reindex` rebuilds it from scratch, and `run_scale_checks.py` asserts the
    # two agree -- so a wrong index is a failed check rather than a wrong answer
    # nobody can trace.
    #
    # Matching is on the normalized body, which is why `Ayse` finds `Ayşe`: the
    # same normalization the previous query was already applying to names.
    candidate_ids = search_index.search(db, probe, limit=limit)

    results = []
    seen_work_ids = set()

    for work_id in candidate_ids:
        work_detail = build_work_detail(
            work_entity_id=work_id,
            db=db,
        )

        if work_detail is None:
            continue

        canonical_work_entity_id = work_detail["entity_id"]

        if canonical_work_entity_id in seen_work_ids:
            continue

        seen_work_ids.add(canonical_work_entity_id)
        results.append(work_detail)

    return {
        "query": q,
        "count": len(results),
        "limit": limit,
        # The index caps at `limit` before duplicates are collapsed, so a full
        # page is the honest signal that more may exist. Real pagination needs
        # the Search Plane (docs/architecture-v2.md §9); until then the client
        # is told the result set was cut rather than being left to assume it
        # saw everything.
        "truncated": len(candidate_ids) >= limit,
        "results": results,
    }
