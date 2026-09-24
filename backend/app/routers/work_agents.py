from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Entity,
    Work,
    Person,
    CollectiveAgent,
    WorkAgentRelation,
)


router = APIRouter(
    prefix="/works",
    tags=["work-agents"],
)


class AgentRelationCreate(BaseModel):
    agent_entity_id: UUID
    role: str


@router.post("/{work_entity_id}/agents", status_code=201)
def add_work_agent(
    work_entity_id: UUID,
    payload: AgentRelationCreate,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    agent = db.get(Entity, payload.agent_entity_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agent entity not found",
        )

    if agent.entity_type not in {"PERSON", "ORGANIZATION"}:
        raise HTTPException(
            status_code=400,
            detail="Agent must be PERSON or ORGANIZATION",
        )

    existing = (
        db.query(WorkAgentRelation)
        .filter(
            WorkAgentRelation.work_entity_id == work_entity_id,
            WorkAgentRelation.agent_entity_id == payload.agent_entity_id,
            WorkAgentRelation.role == payload.role,
        )
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This work-agent relation already exists",
        )

    relation = WorkAgentRelation(
        work_entity_id=work_entity_id,
        agent_entity_id=payload.agent_entity_id,
        role=payload.role,
    )

    db.add(relation)
    db.commit()

    return {
        "work_entity_id": str(work_entity_id),
        "agent_entity_id": str(payload.agent_entity_id),
        "role": payload.role,
    }


@router.get("/{work_entity_id}/agents")
def get_work_agents(
    work_entity_id: UUID,
    db: Session = Depends(get_db),
):
    work = db.get(Work, work_entity_id)

    if work is None:
        raise HTTPException(
            status_code=404,
            detail="Work not found",
        )

    relations = (
        db.query(WorkAgentRelation)
        .filter(
            WorkAgentRelation.work_entity_id == work_entity_id
        )
        .all()
    )

    agents = []

    for relation in relations:
        entity = db.get(
            Entity,
            relation.agent_entity_id,
        )

        if entity is None:
            continue

        canonical_name = None

        if entity.entity_type == "PERSON":
            person = db.get(
                Person,
                relation.agent_entity_id,
            )

            if person is not None:
                canonical_name = person.canonical_name

        elif entity.entity_type == "ORGANIZATION":
            organization = db.get(
                CollectiveAgent,
                relation.agent_entity_id,
            )

            if organization is not None:
                canonical_name = organization.canonical_name

        agents.append(
            {
                "agent_entity_id": str(
                    relation.agent_entity_id
                ),
                "entity_type": entity.entity_type,
                "canonical_name": canonical_name,
                "role": relation.role,
            }
        )

    return {
        "work_entity_id": str(work_entity_id),
        "agents": agents,
    }