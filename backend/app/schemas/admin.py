"""Request models for admin."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["ProposalDecision"]


class ProposalDecision(BaseModel):
    """What a reviewer decided, and why.

    `reviewed_by` is not part of this: it comes from the authenticated session,
    not from the caller. A body that could name its own reviewer would record
    whoever the client felt like claiming.
    """

    decision: str = Field(pattern="^(accepted|rejected)$")

    note: str | None = Field(
        default=None,
        max_length=2000,
        description="Kararın gerekçesi; kayıt altına alınır.",
    )
