"""Request models for reconciliation."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


__all__ = ["ReconciliationDecisionCreate"]


class ReconciliationDecisionCreate(BaseModel):
    candidate_id: uuid.UUID | None = None

    status: str = Field(
        pattern="^(accepted|rejected|unresolved|new_entity)$",
    )

    origin: str = Field(
        default="manual",
        pattern="^(manual|automatic)$",
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    reason: str | None = None

    decision_method: str | None = Field(
        default=None,
        max_length=100,
    )

    reviewed_by: str | None = Field(
        default=None,
        max_length=200,
    )
