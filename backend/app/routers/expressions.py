from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..ids import uuid7
from ..models import Entity, Expression, Work
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["expressions"])


class ExpressionCreate(BaseModel):
    work_entity_id: UUID
    language: str | None = Field(default=None, max_length=100)
    expression_form: str | None = Field(default=None, max_length=100)
    description: str | None = None


@router.post("/expressions", status_code=201)
def create_expression(
    payload: ExpressionCreate,
    db: Session = Depends(get_db),
):
    canonical_work_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=payload.work_entity_id,
    )

    work = db.get(Work, canonical_work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    entity_id = uuid7()

    entity = Entity(
        id=entity_id,
        entity_type="EXPRESSION",
    )

    expression = Expression(
        entity_id=entity_id,
        language=payload.language,
        expression_form=payload.expression_form,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.add(expression)
        db.flush()

        db.execute(
            text("""
                INSERT INTO work_expression (
                    work_entity_id,
                    expression_entity_id
                )
                VALUES (
                    :work_entity_id,
                    :expression_entity_id
                )
            """),
            {
                "work_entity_id": canonical_work_entity_id,
                "expression_entity_id": entity_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "EXPRESSION",
        "work_entity_id": str(canonical_work_entity_id),
        "language": expression.language,
        "expression_form": expression.expression_form,
    }