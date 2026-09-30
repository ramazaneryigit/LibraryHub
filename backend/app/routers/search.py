from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Concept
from ..services.work_detail import build_work_detail
from ..services.entity_merge import resolve_canonical_entity_id


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

    search_term = f"%{q.strip()}%"

    query = """
    SELECT DISTINCT
        w.entity_id,
        w.canonical_title
    FROM works w

    -- Work tanımlayıcıları
    LEFT JOIN identifiers work_identifier
      ON work_identifier.entity_id = w.entity_id

    -- Work yazarları / yaratıcıları
    LEFT JOIN work_agent_relation war
      ON war.work_entity_id = w.entity_id
    LEFT JOIN persons work_person
      ON work_person.entity_id = war.agent_entity_id

    -- Work kişilerinin Nomen kayıtları
    LEFT JOIN nomens work_person_nomen
      ON work_person_nomen.entity_id = work_person.entity_id

    -- Work kişilerinin tanımlayıcıları
    LEFT JOIN identifiers work_person_identifier
      ON work_person_identifier.entity_id = work_person.entity_id

    -- Work konuları
    LEFT JOIN entity_relation subject_rel
      ON subject_rel.subject_entity_id = w.entity_id
     AND subject_rel.predicate = 'has_subject'
    LEFT JOIN concepts concept
      ON concept.entity_id = subject_rel.object_entity_id

    -- Work -> Expression
    LEFT JOIN work_expression we
      ON we.work_entity_id = w.entity_id
    LEFT JOIN expressions expression
      ON expression.entity_id = we.expression_entity_id

    -- Expression tanımlayıcıları
    LEFT JOIN identifiers expression_identifier
      ON expression_identifier.entity_id = expression.entity_id

    -- Expression kişileri (örn. çevirmen)
    LEFT JOIN expression_agent_relation ear
      ON ear.expression_entity_id = expression.entity_id
    LEFT JOIN persons expression_person
      ON expression_person.entity_id = ear.agent_entity_id

    -- Expression kişilerinin Nomen kayıtları
    LEFT JOIN nomens expression_person_nomen
      ON expression_person_nomen.entity_id = expression_person.entity_id

    -- Expression kişilerinin tanımlayıcıları
    LEFT JOIN identifiers expression_person_identifier
      ON expression_person_identifier.entity_id = expression_person.entity_id

    -- Expression -> Manifestation
    LEFT JOIN expression_manifestation em
      ON em.expression_entity_id = expression.entity_id

    LEFT JOIN manifestations manifestation
      ON manifestation.entity_id = em.manifestation_entity_id

    -- Manifestation tanımlayıcıları (ISBN vb.)
    LEFT JOIN identifiers manifestation_identifier
      ON manifestation_identifier.entity_id = manifestation.entity_id

    -- Manifestation ajanları (örn. yayıncı)
    LEFT JOIN manifestation_agent_relation mar
      ON mar.manifestation_entity_id = manifestation.entity_id
    LEFT JOIN collective_agents manifestation_agent
      ON manifestation_agent.entity_id = mar.agent_entity_id

    -- Manifestation ajanının tanımlayıcıları
    LEFT JOIN identifiers manifestation_agent_identifier
      ON manifestation_agent_identifier.entity_id = manifestation_agent.entity_id

    -- Manifestation -> Item
    --
    -- Read through public.items_compat rather than the legacy tables. Copies
    -- live in the tenant plane now, and the view is how a reader outside any
    -- tenant sees them. Its `entity_id` is the same identifier the migrated rows
    -- already had, so the item-level identifiers below still resolve -- which
    -- matters, because two of them are real catalogue numbers rather than
    -- generated ones.
    LEFT JOIN public.items_compat item
      ON item.manifestation_entity_id = manifestation.entity_id

    -- Item tanımlayıcıları
    LEFT JOIN identifiers item_identifier
      ON item_identifier.entity_id = item.entity_id

    WHERE
        w.canonical_title ILIKE :search_term
        OR w.original_title ILIKE :search_term
        OR work_identifier.value ILIKE :search_term
        OR work_person.canonical_name ILIKE :search_term
        OR work_person_nomen.value ILIKE :search_term
        OR work_person_identifier.value ILIKE :search_term
        OR concept.preferred_label ILIKE :search_term
        OR expression.language ILIKE :search_term
        OR expression_identifier.value ILIKE :search_term
        OR expression_person.canonical_name ILIKE :search_term
        OR expression_person_nomen.value ILIKE :search_term
        OR expression_person_identifier.value ILIKE :search_term
        OR manifestation.publication_statement ILIKE :search_term
        OR manifestation.publication_date ILIKE :search_term
        OR manifestation.edition_statement ILIKE :search_term
        OR manifestation_identifier.value ILIKE :search_term
        OR manifestation_agent.canonical_name ILIKE :search_term
        OR manifestation_agent_identifier.value ILIKE :search_term
        OR item.barcode ILIKE :search_term
        OR item.shelfmark ILIKE :search_term
        OR item_identifier.value ILIKE :search_term

    ORDER BY w.canonical_title
    LIMIT :limit
    """

    rows = db.execute(
        text(query),
        {"search_term": search_term, "limit": limit},
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
        results.append(work_detail)

    return {
        "query": q,
        "count": len(results),
        "limit": limit,
        # The SQL caps at `limit` before duplicates are collapsed, so a full
        # page is the honest signal that more may exist. Real pagination needs
        # the Search Plane (docs/architecture-v2.md §9); until then the client
        # is told the result set was cut rather than being left to assume it
        # saw everything.
        "truncated": len(rows) >= limit,
        "results": results,
    }