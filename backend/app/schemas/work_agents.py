"""Request models for work_agents."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


__all__ = ["AgentRelationCreate"]


class AgentRelationCreate(BaseModel):
    agent_entity_id: UUID
    role: str
