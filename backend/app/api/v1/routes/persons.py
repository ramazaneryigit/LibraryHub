from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ....db import get_db
from ....core.ids import uuid7
from ....db.models import Entity, Identifier, Nomen, Person
from ....services.entity_merge import (
    create_entity_merge,
    resolve_canonical_entity_id,
)
from ....services.work_detail import build_work_detail


router = APIRouter(
    prefix="/persons",
    tags=["persons"],
)


class PersonCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    given_name: str | None = Field(default=None, max_length=250)
    family_name: str | None = Field(default=None, max_length=250)
    biography: str | None = None

class NomenCreate(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=100)
    script: str | None = Field(default=None, max_length=50)
    nomen_type: str | None = Field(default=None, max_length=100)
    preferred: bool = False

def find_person_duplicates(
    db: Session,
    name: str,
):
    normalized_name = name.strip()

    rows = db.execute(
        text("""
            SELECT DISTINCT
                p.entity_id,
                p.canonical_name,
                CASE
                    WHEN LOWER(TRIM(p.canonical_name))
                         = LOWER(TRIM(:name))
                    THEN 'canonical_name'

                    WHEN LOWER(TRIM(n.value))
                         = LOWER(TRIM(:name))
                    THEN 'nomen'

                    ELSE 'unknown'
                END AS match_reason
            FROM persons p

            LEFT JOIN nomens n
              ON n.entity_id = p.entity_id

            WHERE
                LOWER(TRIM(p.canonical_name))
                    = LOWER(TRIM(:name))

                OR

                LOWER(TRIM(n.value))
                    = LOWER(TRIM(:name))

            ORDER BY p.canonical_name
        """),
        {
            "name": normalized_name,
        },
    ).mappings().all()

    return [
        {
            "entity_id": str(row["entity_id"]),
            "canonical_name": row["canonical_name"],
            "match_reason": row["match_reason"],
        }
        for row in rows
    ]


@router.post("", status_code=201)
def create_person(
    payload: PersonCreate,
    force_create: bool = False,
    db: Session = Depends(get_db),
):
    candidates = find_person_duplicates(
        db=db,
        name=payload.canonical_name,
    )

    if candidates and not force_create:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Possible duplicate person found",
                "query": payload.canonical_name.strip(),
                "count": len(candidates),
                "candidates": candidates,
                "hint": (
                    "Review the candidates. "
                    "If this is a different person, "
                    "retry with force_create=true."
                ),
            },
        )

    entity_id = uuid7()

    entity = Entity(
        id=entity_id,
        entity_type="PERSON",
    )

    person = Person(
        entity_id=entity_id,
        canonical_name=payload.canonical_name,
        given_name=payload.given_name,
        family_name=payload.family_name,
        biography=payload.biography,
    )

    primary_nomen = Nomen(
        id=uuid7(),
        entity_id=entity_id,
        value=payload.canonical_name,
        preferred=True,
        nomen_type="preferred_name",
    )

    try:
        db.add(entity)
        db.add(person)
        db.add(primary_nomen)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "PERSON",
        "canonical_name": person.canonical_name,
        "preferred_nomen": primary_nomen.value,
    }


@router.get("")
def list_persons(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count()).select_from(Person)
    )

    offset = (page - 1) * page_size

    persons = db.scalars(
        select(Person)
        .order_by(Person.canonical_name, Person.entity_id)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "entity_id": str(person.entity_id),
                "canonical_name": person.canonical_name,
                "given_name": person.given_name,
                "family_name": person.family_name,
            }
            for person in persons
        ],
    }


@router.get("/duplicate-candidates")
def find_person_duplicate_candidates(
    name: str = Query(min_length=1, max_length=500),
    db: Session = Depends(get_db),
):
    candidates = find_person_duplicates(
        db=db,
        name=name,
    )

    return {
        "query": name.strip(),
        "count": len(candidates),
        "candidates": candidates,
    }


@router.get("/{entity_id}")
def get_person(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db,
        entity_id,
    )

    person = db.get(Person, canonical_entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    nomens = db.scalars(
        select(Nomen)
        .where(Nomen.entity_id == canonical_entity_id)
        .order_by(Nomen.preferred.desc(), Nomen.value)
    ).all()

    return {
        "entity_id": str(person.entity_id),
        "canonical_name": person.canonical_name,
        "given_name": person.given_name,
        "family_name": person.family_name,
        "biography": person.biography,
        "nomens": [
            {
                "id": str(nomen.id),
                "value": nomen.value,
                "language": nomen.language,
                "script": nomen.script,
                "nomen_type": nomen.nomen_type,
                "preferred": nomen.preferred,
            }
            for nomen in nomens
        ],
    }
@router.post("/{entity_id}/nomens", status_code=201)
def create_nomen(
    entity_id: UUID,
    payload: NomenCreate,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db,
        entity_id,
    )

    person = db.get(Person, canonical_entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    nomen = Nomen(
        id=uuid7(),
        entity_id=canonical_entity_id,
        value=payload.value,
        language=payload.language,
        script=payload.script,
        nomen_type=payload.nomen_type,
        preferred=payload.preferred,
    )

    try:
        db.add(nomen)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "id": str(nomen.id),
        "entity_id": str(canonical_entity_id),
        "value": nomen.value,
        "preferred": nomen.preferred,
    }

@router.get("/{entity_id}/works")
def get_person_works(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db,
        entity_id,
    )

    person = db.get(Person, canonical_entity_id)

    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found",
        )

    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                related.entity_id,
                related.role,
                related.relation_level
            FROM (
                -- Kişinin doğrudan Work ile ilişkisi
                SELECT
                    w.entity_id AS entity_id,
                    war.role AS role,
                    'work' AS relation_level
                FROM work_agent_relation war
                JOIN works w
                  ON w.entity_id = war.work_entity_id
                WHERE war.agent_entity_id = :entity_id

                UNION

                -- Kişinin Expression üzerinden Work ile ilişkisi
                SELECT
                    w.entity_id AS entity_id,
                    ear.role AS role,
                    'expression' AS relation_level
                FROM expression_agent_relation ear
                JOIN work_expression we
                  ON we.expression_entity_id = ear.expression_entity_id
                JOIN works w
                  ON w.entity_id = we.work_entity_id
                WHERE ear.agent_entity_id = :entity_id
            ) AS related
            ORDER BY
                related.entity_id,
                related.role
            """
        ),
        {
            "entity_id": canonical_entity_id,
        },
    ).mappings().all()

    works = []

    for row in rows:
        detail = build_work_detail(
            work_entity_id=row["entity_id"],
            db=db,
        )

        if detail is not None:
            works.append(
                {
                    "role": row["role"],
                    "relation_level": row["relation_level"],
                    "work": detail,
                }
            )

    return {
        "entity_id": str(person.entity_id),
        "canonical_name": person.canonical_name,
        "biography": person.biography,
        "works": works,
    }

@router.post("/{source_person_id}/merge/{target_person_id}")
def merge_persons(
    source_person_id: UUID,
    target_person_id: UUID,
    db: Session = Depends(get_db),
):
    if source_person_id == target_person_id:
        raise HTTPException(
            status_code=400,
            detail="Source and target person cannot be the same",
        )

    source_person = db.get(Person, source_person_id)

    canonical_target_person_id = resolve_canonical_entity_id(
        db,
        target_person_id,
    )

    target_person = db.get(
        Person,
        canonical_target_person_id,
    )

    if source_person is None:
        raise HTTPException(
            status_code=404,
            detail="Source person not found",
        )

    if target_person is None:
        raise HTTPException(
            status_code=404,
            detail="Target person not found",
        )

    try:
        # 1. Work-agent relations
        db.execute(
            text("""
                INSERT INTO work_agent_relation (
                    work_entity_id,
                    agent_entity_id,
                    role
                )
                SELECT
                    work_entity_id,
                    :target_id,
                    role
                FROM work_agent_relation
                WHERE agent_entity_id = :source_id
                ON CONFLICT DO NOTHING
            """),
            {
                "source_id": source_person_id,
                "target_id": target_person_id,
            },
        )

        # 2. Expression-agent relations
        db.execute(
            text("""
                INSERT INTO expression_agent_relation (
                    expression_entity_id,
                    agent_entity_id,
                    role
                )
                SELECT
                    expression_entity_id,
                    :target_id,
                    role
                FROM expression_agent_relation
                WHERE agent_entity_id = :source_id
                ON CONFLICT DO NOTHING
            """),
            {
                "source_id": source_person_id,
                "target_id": target_person_id,
            },
        )

        # 3. Manifestation-agent relations
        db.execute(
            text("""
                INSERT INTO manifestation_agent_relation (
                    manifestation_entity_id,
                    agent_entity_id,
                    role
                )
                SELECT
                    manifestation_entity_id,
                    :target_id,
                    role
                FROM manifestation_agent_relation
                WHERE agent_entity_id = :source_id
                ON CONFLICT DO NOTHING
            """),
            {
                "source_id": source_person_id,
                "target_id": target_person_id,
            },
        )

        # 4. Item-agent relations -- deliberately absent.
        #
        # `item_agent_relation` only ever holds institutional custody: every row
        # is an ORGANIZATION under the role `holding_institution`, and none names
        # a PERSON (measured before removing this). A person merge therefore has
        # nothing to move here, and the step was dead code that happened to work.
        # The table itself is legacy, goes in Aşama 6, and custody is structural
        # now -- item -> holding -> branch -> organization.

        # 5. General Entity relations - source side
        db.execute(
            text("""
                INSERT INTO entity_relation (
                    subject_entity_id,
                    predicate,
                    object_entity_id
                )
                SELECT
                    :target_id,
                    predicate,
                    object_entity_id
                FROM entity_relation
                WHERE subject_entity_id = :source_id
                  AND object_entity_id <> :target_id
                ON CONFLICT DO NOTHING
            """),
            {
                "source_id": source_person_id,
                "target_id": target_person_id,
            },
        )

        # 6. General Entity relations - object side
        db.execute(
            text("""
                INSERT INTO entity_relation (
                    subject_entity_id,
                    predicate,
                    object_entity_id
                )
                SELECT
                    subject_entity_id,
                    predicate,
                    :target_id
                FROM entity_relation
                WHERE object_entity_id = :source_id
                  AND subject_entity_id <> :target_id
                ON CONFLICT DO NOTHING
            """),
            {
                "source_id": source_person_id,
                "target_id": target_person_id,
            },
        )

        # 7. Identifiers
        source_identifiers = db.scalars(
            select(Identifier).where(
                Identifier.entity_id == source_person_id
            )
        ).all()

        target_identifiers = db.scalars(
            select(Identifier).where(
                Identifier.entity_id == target_person_id
            )
        ).all()

        for source_identifier in source_identifiers:
            duplicate = any(
                target_identifier.scheme.strip().casefold()
                == source_identifier.scheme.strip().casefold()
                and target_identifier.value.strip().casefold()
                == source_identifier.value.strip().casefold()
                for target_identifier in target_identifiers
            )

            if duplicate:
                continue

            new_identifier = Identifier(
                id=uuid7(),
                entity_id=target_person_id,
                scheme=source_identifier.scheme,
                value=source_identifier.value,
                qualifier=source_identifier.qualifier,
                preferred=False,
            )

            db.add(new_identifier)

        # 8. Nomens
        source_nomens = db.scalars(
            select(Nomen).where(
                Nomen.entity_id == source_person_id
            )
        ).all()

        target_nomens = db.scalars(
            select(Nomen).where(
                Nomen.entity_id == target_person_id
            )
        ).all()

        for source_nomen in source_nomens:
            normalized_source_value = (
                source_nomen.value.strip().casefold()
            )

            duplicate = any(
                target_nomen.value.strip().casefold()
                == normalized_source_value
                for target_nomen in target_nomens
            )

            if duplicate:
                continue

            new_nomen = Nomen(
                id=uuid7(),
                entity_id=target_person_id,
                value=source_nomen.value,
                language=source_nomen.language,
                script=source_nomen.script,
                nomen_type=source_nomen.nomen_type,
                preferred=False,
            )

            db.add(new_nomen)

        # 9. Preserve source Entity and create canonical redirect
        create_entity_merge(
            db,
            source_person_id,
            target_person_id,
            origin="manual",
            merge_method="person_merge",
        )

        # 10. Remove active relations from the merged source Person.
        # Historical/provenance references such as reconciliation candidates
        # remain attached to the preserved source Entity.
        #
        # `item_agent_relation` is not in this list for the same reason it is not
        # moved above: it holds institutional custody, not person attributions.
        for table_name in (
            "work_agent_relation",
            "expression_agent_relation",
            "manifestation_agent_relation",
        ):
            db.execute(
                text(
                    f"DELETE FROM {table_name} "
                    "WHERE agent_entity_id = :source_id"
                ),
                {"source_id": source_person_id},
            )

        db.execute(
            text(
                "DELETE FROM entity_relation "
                "WHERE subject_entity_id = :source_id "
                "OR object_entity_id = :source_id"
            ),
            {"source_id": source_person_id},
        )

        # 11. Remove active source identifiers and nomens after they have
        # been copied to the canonical target.
        db.execute(
            text(
                "DELETE FROM identifiers "
                "WHERE entity_id = :source_id"
            ),
            {"source_id": source_person_id},
        )

        db.execute(
            text(
                "DELETE FROM nomens "
                "WHERE entity_id = :source_id"
            ),
            {"source_id": source_person_id},
        )

        # 12. Remove only the Person subtype row.
        # The source Entity itself is intentionally preserved as a redirect.
        db.delete(source_person)

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    return {
        "status": "merged",
        "source_person_id": str(source_person_id),
        "target_person_id": str(canonical_target_person_id),
        "target_canonical_name": target_person.canonical_name,
    }
