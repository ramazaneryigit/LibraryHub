from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Concept, Entity


router = APIRouter(tags=["concepts"])


class ConceptCreate(BaseModel):
    preferred_label: str = Field(min_length=1, max_length=500)
    definition: str | None = None
    scheme: str | None = Field(default=None, max_length=100)


@router.post("/concepts", status_code=201)
def create_concept(
    payload: ConceptCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="CONCEPT",
    )

    concept = Concept(
        entity_id=entity_id,
        preferred_label=payload.preferred_label,
        definition=payload.definition,
        scheme=payload.scheme,
    )

    try:
        db.add(entity)
        db.flush()

        db.add(concept)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "CONCEPT",
        "preferred_label": concept.preferred_label,
        "scheme": concept.scheme,
    }