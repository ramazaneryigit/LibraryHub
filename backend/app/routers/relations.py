from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Entity, EntityRelation
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(
    prefix="/relations",
    tags=["relations"],
)


class EntityRelationCreate(BaseModel):
    object_entity_id: UUID
    predicate: str = Field(min_length=1, max_length=100)


def get_relation_definition(
    db: Session,
    predicate: str,
):
    row = db.execute(
        text("""
            SELECT
                p.id,
                p.code,
                p.label,
                p.description,
                p.source_scheme,
                p.uri,
                p."symmetric",
                p.transitive,
                i.code AS inverse
            FROM relation_predicates p
            LEFT JOIN relation_predicates i
                ON i.id = p.inverse_predicate_id
            WHERE p.code = :predicate
        """),
        {
            "predicate": predicate,
        },
    ).mappings().first()

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "code": row["code"],
        "label": row["label"],
        "description": row["description"],
        "source_scheme": row["source_scheme"],
        "uri": row["uri"],
        "inverse": row["inverse"],
        "symmetric": row["symmetric"],
        "transitive": row["transitive"],
    }


def build_entity_relations(
    db: Session,
    entity_id: UUID,
):
    rows = db.execute(
        text("""
            SELECT
                er.subject_entity_id,
                er.predicate,
                er.object_entity_id
            FROM entity_relation er
            WHERE er.subject_entity_id = :entity_id
               OR er.object_entity_id = :entity_id
            ORDER BY er.predicate
        """),
        {
            "entity_id": str(entity_id),
        },
    ).fetchall()

    relations = []

    for row in rows:
        subject_id = row.subject_entity_id
        predicate = row.predicate
        object_id = row.object_entity_id

        definition = get_relation_definition(
            db,
            predicate,
        )

        if str(subject_id) == str(entity_id):
            direction = "outgoing"
            related_entity_id = object_id
        else:
            direction = "incoming"
            related_entity_id = subject_id

        relation_item = {
            "direction": direction,
            "predicate": predicate,
            "related_entity_id": str(related_entity_id),
        }

        if definition:
            relation_item["inverse"] = definition["inverse"]
            relation_item["symmetric"] = definition["symmetric"]

        relations.append(relation_item)

    return relations


@router.get("/{entity_id}")
def list_entity_relations(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    """Entity ile ilişkili tüm ilişkileri listeler (gelen ve giden)."""

    canonical_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=entity_id,
    )

    entity = db.get(Entity, canonical_entity_id)

    if entity is None:
        raise HTTPException(
            status_code=404,
            detail="Entity not found",
        )

    relations = build_entity_relations(
        db,
        canonical_entity_id,
    )

    return {
        "entity_id": str(canonical_entity_id),
        "relations": relations,
    }

@router.post("/{entity_id}", status_code=201)
def create_entity_relation(
    entity_id: UUID,
    payload: EntityRelationCreate,
    db: Session = Depends(get_db),
):
    """Entity'ler arasında yeni bir ilişki oluşturur ve tüm ilişkileri döndürür."""

    canonical_subject_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=entity_id,
    )

    canonical_object_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=payload.object_entity_id,
    )

    subject = db.get(
        Entity,
        canonical_subject_entity_id,
    )

    if subject is None:
        raise HTTPException(
            status_code=404,
            detail="Subject entity not found",
        )

    object_entity = db.get(
        Entity,
        canonical_object_entity_id,
    )

    if object_entity is None:
        raise HTTPException(
            status_code=404,
            detail="Object entity not found",
        )

    predicate = payload.predicate.strip()

    definition = get_relation_definition(
        db,
        predicate,
    )

    if definition is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown relation predicate: {predicate}",
        )

    constraint_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM relation_predicate_constraints
            WHERE predicate_id = :predicate_id
        """),
        {
            "predicate_id": definition["id"],
        },
    ).scalar_one()

    if constraint_count > 0:
        allowed = db.execute(
            text("""
                SELECT 1
                FROM relation_predicate_constraints
                WHERE predicate_id = :predicate_id
                  AND subject_entity_type = :subject_entity_type
                  AND object_entity_type = :object_entity_type
                LIMIT 1
            """),
            {
                "predicate_id": definition["id"],
                "subject_entity_type": subject.entity_type,
                "object_entity_type": object_entity.entity_type,
            },
        ).first()

        if allowed is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Relation predicate '{predicate}' is not allowed "
                    f"from {subject.entity_type} "
                    f"to {object_entity.entity_type}"
                ),
            )

    relation = EntityRelation(
        subject_entity_id=canonical_subject_entity_id,
        predicate=predicate,
        object_entity_id=canonical_object_entity_id,
    )

    try:
        db.add(relation)
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="This entity relation already exists",
        )

    relations = build_entity_relations(
        db,
        canonical_subject_entity_id,
    )

    return {
        "entity_id": str(canonical_subject_entity_id),
        "relations": relations,
    }