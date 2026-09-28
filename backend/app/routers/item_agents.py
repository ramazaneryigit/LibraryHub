from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    CollectiveAgent,
    Entity,
    Item,
    ItemAgentRelation,
    Person,
)


router = APIRouter(tags=["item-agents"])


class AgentRelationCreate(BaseModel):
    agent_entity_id: UUID
    role: str = Field(min_length=1, max_length=100)


@router.post("/items/{item_entity_id}/agents", status_code=201)
def add_item_agent(
    item_entity_id: UUID,
    payload: AgentRelationCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_entity_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
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
            detail="Entity is not an Agent",
        )

    relation = ItemAgentRelation(
        item_entity_id=item_entity_id,
        agent_entity_id=payload.agent_entity_id,
        role=payload.role,
    )

    try:
        db.add(relation)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This Item-Agent relation already exists",
        )

    return {
        "item_entity_id": str(item_entity_id),
        "agent_entity_id": str(payload.agent_entity_id),
        "role": payload.role,
    }


@router.get("/items/{item_entity_id}/agents")
def list_item_agents(
    item_entity_id: UUID,
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_entity_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
        )

    relations = db.scalars(
        select(ItemAgentRelation)
        .where(
            ItemAgentRelation.item_entity_id == item_entity_id
        )
        .order_by(ItemAgentRelation.role)
    ).all()

    result = []

    for relation in relations:
        agent = db.get(Entity, relation.agent_entity_id)

        if agent is None:
            continue

        if agent.entity_type == "PERSON":
            person = db.get(Person, relation.agent_entity_id)

            if person is not None:
                result.append(
                    {
                        "entity_id": str(person.entity_id),
                        "entity_type": "PERSON",
                        "name": person.canonical_name,
                        "role": relation.role,
                    }
                )

        elif agent.entity_type == "ORGANIZATION":
            organization = db.get(
                CollectiveAgent,
                relation.agent_entity_id,
            )

            result.append(
                {
                    "entity_id": str(agent.id),
                    "entity_type": "ORGANIZATION",
                    "name": (
                        organization.canonical_name
                        if organization is not None
                        else None
                    ),
                    "role": relation.role,
                }
            )

    return result