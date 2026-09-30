from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ...deps import require_staff
from ....services.entity_merge import resolve_canonical_entity_id

from ....db import get_db
from ....db.models import Entity, Identifier
from ....schemas.identifiers import IdentifierCreate


router = APIRouter(tags=["identifiers"])


@router.get("/entities/{entity_id}/identifiers")
def get_entity_identifiers(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db,
        entity_id,
    )

    entity = db.get(Entity, canonical_entity_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    identifiers = db.execute(
        select(Identifier)
        .where(Identifier.entity_id == canonical_entity_id)
        .order_by(
            Identifier.preferred.desc(),
            Identifier.scheme,
            Identifier.value,
        )
    ).scalars().all()

    return {
        "entity_id": str(canonical_entity_id),
        "entity_type": entity.entity_type,
        "identifiers": [
            {
                "id": str(identifier.id),
                "scheme": identifier.scheme,
                "value": identifier.value,
                "qualifier": identifier.qualifier,
                "preferred": identifier.preferred,
            }
            for identifier in identifiers
        ],
    }

@router.post("/entities/{entity_id}/identifiers", status_code=201, dependencies=[Depends(require_staff)])
def create_entity_identifier(
    entity_id: UUID,
    payload: IdentifierCreate,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db,
        entity_id,
    )

    entity = db.get(Entity, canonical_entity_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    identifier = Identifier(
        entity_id=canonical_entity_id,
        scheme=payload.scheme.strip().lower(),
        value=payload.value.strip(),
        qualifier=payload.qualifier.strip() if payload.qualifier else None,
        preferred=payload.preferred,
    )

    db.add(identifier)

    try:
        db.commit()
        db.refresh(identifier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This identifier already exists for this entity",
        )

    return {
        "id": str(identifier.id),
        "entity_id": str(identifier.entity_id),
        "scheme": identifier.scheme,
        "value": identifier.value,
        "qualifier": identifier.qualifier,
        "preferred": identifier.preferred,
    }