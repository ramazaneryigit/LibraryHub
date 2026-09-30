from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...deps import require_staff
from ....db import get_db
from ....core.ids import uuid7
from ....db.models import Entity, Work
from ....services.work_detail import build_work_detail
from ....services.entity_merge import resolve_canonical_entity_id


router = APIRouter(
    prefix="/works",
    tags=["works"],
)


class WorkCreate(BaseModel):
    canonical_title: str
    original_title: str | None = None
    original_language: str | None = None
    work_type: str | None = None
    description: str | None = None


@router.get("")
def list_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count()).select_from(Work)
    )

    offset = (page - 1) * page_size

    works = db.scalars(
        select(Work)
        .order_by(Work.canonical_title, Work.entity_id)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "entity_id": str(work.entity_id),
                "canonical_title": work.canonical_title,
                "original_title": work.original_title,
                "original_language": work.original_language,
            }
            for work in works
        ],
    }


@router.post("", status_code=201, dependencies=[Depends(require_staff)])
def create_work(
    payload: WorkCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid7()

    entity = Entity(
        id=entity_id,
        entity_type="WORK",
    )

    work = Work(
        entity_id=entity_id,
        canonical_title=payload.canonical_title,
        original_title=payload.original_title,
        original_language=payload.original_language,
        work_type=payload.work_type,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.add(work)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "WORK",
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
        "work_type": work.work_type,
    }


@router.get("/{entity_id}")
def get_work(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=entity_id,
    )

    work = db.get(Work, canonical_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    return {
        "entity_id": str(work.entity_id),
        "canonical_title": work.canonical_title,
        "original_title": work.original_title,
        "original_language": work.original_language,
        "work_type": work.work_type,
        "description": work.description,
    }
    
@router.get("/{work_entity_id}/detail")
def get_work_detail(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    result = build_work_detail(
        work_entity_id=work_entity_id,
        db=db,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    return result