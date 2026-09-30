from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..ids import uuid7
from ..models import Entity, Expression, Manifestation
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["manifestations"])


class ManifestationCreate(BaseModel):
    expression_entity_id: UUID
    publication_statement: str | None = Field(default=None, max_length=1000)
    publication_date: str | None = Field(default=None, max_length=100)
    edition_statement: str | None = Field(default=None, max_length=500)
    carrier_type: str | None = Field(default=None, max_length=100)
    extent: str | None = Field(default=None, max_length=500)
    notes: str | None = None


@router.post("/manifestations", status_code=201)
def create_manifestation(
    payload: ManifestationCreate,
    db: Session = Depends(get_db),
):
    canonical_expression_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=payload.expression_entity_id,
    )

    expression = db.get(
        Expression,
        canonical_expression_entity_id,
    )

    if expression is None:
        raise HTTPException(
            status_code=404,
            detail="Expression not found",
        )

    entity_id = uuid7()

    entity = Entity(
        id=entity_id,
        entity_type="MANIFESTATION",
    )

    manifestation = Manifestation(
        entity_id=entity_id,
        publication_statement=payload.publication_statement,
        publication_date=payload.publication_date,
        edition_statement=payload.edition_statement,
        carrier_type=payload.carrier_type,
        extent=payload.extent,
        notes=payload.notes,
    )

    try:
        db.add(entity)
        db.add(manifestation)
        db.flush()

        db.execute(
            text("""
                INSERT INTO expression_manifestation (
                    expression_entity_id,
                    manifestation_entity_id
                )
                VALUES (
                    :expression_entity_id,
                    :manifestation_entity_id
                )
            """),
            {
                "expression_entity_id": canonical_expression_entity_id,
                "manifestation_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "MANIFESTATION",
        "expression_entity_id": str(canonical_expression_entity_id),
        "publication_statement": manifestation.publication_statement,
        "publication_date": manifestation.publication_date,
    }