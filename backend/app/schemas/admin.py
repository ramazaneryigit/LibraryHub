"""Request models for admin."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["ProposalDecision", "UserCreate", "UserUpdate", "PasswordReset"]


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


class UserCreate(BaseModel):
    """A staff account an administrator is opening.

    The role pattern has no `admin` in it, and that is the same rule the database
    enforces. Stating it here turns a refusal into a validation error with a field
    name on it, rather than a 409 from a trigger.

    `account_kind` and `email_verified_at` are absent for the same reason: the
    first is derived from the domain, and the account has to be verified by its
    holder. `tenant_id` is present because a platform administrator has none and
    is opening the account *for* an institution.
    """

    tenant_id: UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=2, max_length=300)
    role: str = Field(default="librarian", pattern="^(librarian|viewer)$")
    password: str = Field(min_length=10, max_length=200)


class UserUpdate(BaseModel):
    """What an administrator may change about an ordinary account."""

    display_name: str | None = Field(default=None, min_length=2, max_length=300)
    role: str | None = Field(default=None, pattern="^(librarian|viewer)$")
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=200)
