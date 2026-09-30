from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...deps import require_staff
from ....db import get_db
from ....core.ids import uuid7
from ....db.models import Concept, Entity
from ....schemas.concepts import ConceptCreate


router = APIRouter(tags=["concepts"])


@router.post("/concepts", status_code=201, dependencies=[Depends(require_staff)])
def create_concept(
    payload: ConceptCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid7()

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