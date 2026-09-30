from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..ids import uuid7
from ..models import CollectiveAgent, Entity
from ..services.work_detail import build_work_detail
from ..services.entity_merge import resolve_canonical_entity_id


router = APIRouter(tags=["collective-agents"])


class CollectiveAgentCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    agent_type: str = Field(min_length=1, max_length=100)
    description: str | None = None


@router.post("/collective-agents", status_code=201)
def create_collective_agent(
    payload: CollectiveAgentCreate,
    db: Session = Depends(get_db),
):
    entity_id = uuid7()

    entity = Entity(
        id=entity_id,
        entity_type="ORGANIZATION",
    )

    agent = CollectiveAgent(
        entity_id=entity_id,
        canonical_name=payload.canonical_name,
        agent_type=payload.agent_type,
        description=payload.description,
    )

    try:
        db.add(entity)
        db.flush()

        db.add(agent)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "entity_id": str(entity_id),
        "entity_type": "ORGANIZATION",
        "canonical_name": agent.canonical_name,
        "agent_type": agent.agent_type,
    }


@router.get("/collective-agents/{entity_id}/works")
def get_collective_agent_works(
    entity_id: UUID,
    db: Session = Depends(get_db),
):
    canonical_entity_id = resolve_canonical_entity_id(
        db=db,
        entity_id=entity_id,
    )

    agent = db.get(CollectiveAgent, canonical_entity_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Collective agent not found",
        )

    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                related.entity_id,
                related.role,
                related.relation_level
            FROM (
                -- Collective Agent -> Manifestation -> Expression -> Work
                SELECT
                    w.entity_id AS entity_id,
                    mar.role AS role,
                    'manifestation' AS relation_level
                FROM manifestation_agent_relation mar
                JOIN expression_manifestation em
                  ON em.manifestation_entity_id = mar.manifestation_entity_id
                JOIN work_expression we
                  ON we.expression_entity_id = em.expression_entity_id
                JOIN works w
                  ON w.entity_id = we.work_entity_id
                WHERE mar.agent_entity_id = :entity_id

                UNION

                -- Collective Agent -> Item -> Manifestation -> Expression -> Work
                SELECT
                    w.entity_id AS entity_id,
                    iar.role AS role,
                    'item' AS relation_level
                FROM item_agent_relation iar
                JOIN manifestation_item mi
                  ON mi.item_entity_id = iar.item_entity_id
                JOIN expression_manifestation em
                  ON em.manifestation_entity_id = mi.manifestation_entity_id
                JOIN work_expression we
                  ON we.expression_entity_id = em.expression_entity_id
                JOIN works w
                  ON w.entity_id = we.work_entity_id
                WHERE iar.agent_entity_id = :entity_id
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
        "entity_id": str(agent.entity_id),
        "canonical_name": agent.canonical_name,
        "agent_type": agent.agent_type,
        "description": agent.description,
        "works": works,
    }