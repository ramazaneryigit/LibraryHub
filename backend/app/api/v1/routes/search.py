from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....core.text import normalize_text
from ....db import get_db
from ....db.models import Concept
from ....services import search_index, semantic_search
from ....services.semantic_search import SemanticSearchError
from ....services.work_detail import build_work_detail
from ....services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["search"])


def _merge_named_records(existing, incoming, *, key_field: str):
    merged = {}

    for item in [*(existing or []), *(incoming or [])]:
        if item is None:
            continue

        identity = str(item.get(key_field) or item.get("name") or item.get("label") or "")

        if not identity:
            identity = str(item)

        merged.setdefault(identity, item)

    return list(merged.values())


def _merge_expression_records(existing, incoming):
    merged_by_id = {}

    for expression in [*(existing or []), *(incoming or [])]:
        if expression is None:
            continue

        expression_id = str(expression.get("entity_id") or "")
        if not expression_id:
            expression_id = str(expression)

        if expression_id not in merged_by_id:
            merged_by_id[expression_id] = dict(expression)
            merged_by_id[expression_id]["manifestations"] = list(
                expression.get("manifestations") or []
            )
            continue

        merged = merged_by_id[expression_id]
        merged["manifestations"] = _merge_named_records(
            merged.get("manifestations", []),
            expression.get("manifestations", []),
            key_field="entity_id",
        )

        for field in ("language", "expression_form", "description", "identifiers", "nomens", "agents"):
            if field in expression and expression[field]:
                merged[field] = _merge_named_records(
                    merged.get(field, []),
                    expression.get(field, []),
                    key_field="entity_id" if field != "identifiers" else "id",
                )

    return list(merged_by_id.values())


def _primary_author_tokens(work_detail):
    authors = (work_detail or {}).get("authors", [])

    primary_names = []
    for author in authors:
        name = (author or {}).get("name")
        if not name:
            continue

        role = str((author or {}).get("role") or "").strip().lower()
        if role and role not in {"author", "creator", "main_author", "primary_author"}:
            continue

        primary_names.append(name)

    if not primary_names:
        primary_names = [
            (author or {}).get("name")
            for author in authors
            if (author or {}).get("name")
        ]

    author_tokens = set()
    for name in primary_names:
        normalized = normalize_text(name) or ""
        author_tokens.update(
            token for token in normalized.replace(",", " ").split() if token
        )

    return tuple(sorted(author_tokens))


def _work_result_key(work_detail):
    title = normalize_text((work_detail or {}).get("canonical_title") or "")
    return (title, _primary_author_tokens(work_detail))


def _merge_duplicate_work_details(work_details):
    merged_by_key = {}

    for work_detail in work_details:
        work_key = _work_result_key(work_detail)

        if work_key not in merged_by_key:
            merged_by_key[work_key] = work_detail
            continue

        current = merged_by_key[work_key]
        current["authors"] = _merge_named_records(
            current.get("authors", []),
            work_detail.get("authors", []),
            key_field="entity_id",
        )
        current["subjects"] = _merge_named_records(
            current.get("subjects", []),
            work_detail.get("subjects", []),
            key_field="entity_id",
        )
        current["expressions"] = _merge_expression_records(
            current.get("expressions", []),
            work_detail.get("expressions", []),
        )

    return list(merged_by_key.values())


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
        "results": _merge_duplicate_work_details(results),
    }

@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    work_type: str | None = Query(default=None, max_length=50),
    language: str | None = Query(default=None, max_length=50),
    year: str | None = Query(default=None, pattern="^[0-9]{4}$"),
    library_id: UUID | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    search_mode: Literal["keyword", "semantic"] = Query(default="keyword"),
    search_field: str | None = Query(
        default=None,
        pattern="^(all|title|author|publisher|isbn|issn|doi|orcid|university|inventory)$",
    ),
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

    # Candidates and facets come from the derived index, not from a
    # twenty-condition join.
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
    semantic_matches = None
    if search_mode == "semantic":
        try:
            semantic_matches = semantic_search.search(probe)
        except SemanticSearchError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        page = search_index.search_page(
            db,
            probe,
            limit=limit,
            cursor=cursor,
            work_type=work_type,
            language=language,
            year=year,
            library_id=library_id,
            subject_id=subject_id,
            search_field=search_field,
            semantic_matches=semantic_matches,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    candidate_ids = page["work_ids"]

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

    results = _merge_duplicate_work_details(results)

    return {
        "query": q,
        "search_mode": search_mode,
        "count": len(results),
        "total": page["total"],
        "limit": limit,
        "truncated": page["has_more"],
        "has_more": page["has_more"],
        "next_cursor": page["next_cursor"],
        "facets": page["facets"],
        "institutions": page["institutions"],
        "filters": {
            "work_type": work_type,
            "language": language,
            "year": year,
            "library_id": str(library_id) if library_id else None,
            "subject_id": str(subject_id) if subject_id else None,
            "search_field": search_field,
        },
        "results": results,
    }
