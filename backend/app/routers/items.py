from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Entity, Item, Manifestation
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["items"])


class ItemCreate(BaseModel):
    manifestation_entity_id: UUID
    barcode: str | None = Field(default=None, max_length=200)
    shelfmark: str | None = Field(default=None, max_length=500)
    condition: str | None = Field(default=None, max_length=100)
    availability_status: str | None = Field(default=None, max_length=100)
    notes: str | None = None


@router.post("/items", status_code=201)
def create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
):
    canonical_manifestation_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=payload.manifestation_entity_id,
    )

    manifestation = db.get(
        Manifestation,
        canonical_manifestation_entity_id,
    )

    if manifestation is None:
        raise HTTPException(
            status_code=404,
            detail="Manifestation not found",
        )

    entity_id = uuid4()

    entity = Entity(
        id=entity_id,
        entity_type="ITEM",
    )

    item = Item(
        entity_id=entity_id,
        barcode=payload.barcode,
        shelfmark=payload.shelfmark,
        condition=payload.condition,
        availability_status=payload.availability_status,
        notes=payload.notes,
    )

    try:
        db.add(entity)
        db.add(item)
        db.flush()

        db.execute(
            text("""
                INSERT INTO manifestation_item (
                    manifestation_entity_id,
                    item_entity_id
                )
                VALUES (
                    :manifestation_entity_id,
                    :item_entity_id
                )
            """),
            {
                "manifestation_entity_id": canonical_manifestation_entity_id,
                "item_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "ITEM",
        "manifestation_entity_id": str(
            canonical_manifestation_entity_id
        ),
        "barcode": item.barcode,
        "shelfmark": item.shelfmark,
        "availability_status": item.availability_status,
    }