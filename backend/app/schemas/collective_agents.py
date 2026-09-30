"""Request models for collective_agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["CollectiveAgentCreate"]


class CollectiveAgentCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    agent_type: str = Field(min_length=1, max_length=100)
    description: str | None = None
