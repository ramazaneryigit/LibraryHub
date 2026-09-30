"""Request models for tenant."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


__all__ = ["HoldingCreate", "HoldingUpdate", "ItemCreate", "ItemUpdate", "FieldChange", "ProposalCreate"]


class HoldingCreate(BaseModel):
    """A new holding for the caller's own institution.

    `tenant_id` is absent on purpose. It comes from the authenticated account and
    never from the request: accepting it would let one institution file records
    under another, and the policy's WITH CHECK half would refuse it anyway.
    """

    branch_id: UUID
    local_holding_key: str = Field(min_length=1, max_length=300)
    manifestation_entity_id: UUID | None = None
    expression_entity_id: UUID | None = None
    holding_type: str = "physical"
    collection_code: str | None = Field(default=None, max_length=100)
    call_number: str | None = Field(default=None, max_length=300)
    call_number_scheme: str | None = Field(default=None, max_length=50)
    holding_statement: str | None = None
    enumeration_pattern: str | None = Field(default=None, max_length=500)
    access_url: str | None = Field(default=None, max_length=1000)
    license_note: str | None = None
    acquisition_source: str | None = Field(default=None, max_length=500)
    public_note: str | None = None
    staff_note: str | None = None
    status: str = "active"


class HoldingUpdate(BaseModel):
    holding_type: str | None = None
    collection_code: str | None = Field(default=None, max_length=100)
    call_number: str | None = Field(default=None, max_length=300)
    call_number_scheme: str | None = Field(default=None, max_length=50)
    holding_statement: str | None = None
    enumeration_pattern: str | None = Field(default=None, max_length=500)
    access_url: str | None = Field(default=None, max_length=1000)
    license_note: str | None = None
    acquisition_source: str | None = Field(default=None, max_length=500)
    public_note: str | None = None
    staff_note: str | None = None
    status: str | None = None


class ItemCreate(BaseModel):
    holding_id: UUID
    barcode: str | None = Field(default=None, max_length=200)
    accession_number: str | None = Field(default=None, max_length=200)
    item_type: str | None = Field(default=None, max_length=50)
    shelfmark: str | None = Field(default=None, max_length=300)
    condition: str | None = Field(default=None, max_length=200)
    availability_status: str = "unknown"
    notes: str | None = None
    donor: str | None = Field(default=None, max_length=500)
    lifecycle_status: str = "active"


class ItemUpdate(BaseModel):
    barcode: str | None = Field(default=None, max_length=200)
    accession_number: str | None = Field(default=None, max_length=200)
    item_type: str | None = Field(default=None, max_length=50)
    shelfmark: str | None = Field(default=None, max_length=300)
    condition: str | None = Field(default=None, max_length=200)
    availability_status: str | None = None
    notes: str | None = None
    donor: str | None = Field(default=None, max_length=500)
    lifecycle_status: str | None = None


class FieldChange(BaseModel):
    field: str = Field(min_length=1, max_length=100)
    current: str | None = Field(default=None, max_length=2000)
    proposed: str | None = Field(default=None, max_length=2000)


class ProposalCreate(BaseModel):
    """A request to change something on the global plane.

    The controlled vocabularies (`change_type`, `status`) are not repeated as
    enums here: the table has check constraints for them, and two copies of the
    same rule drift apart with the database being the one that is right.
    """

    change_type: str = "correction"
    target_entity_type: str | None = Field(default=None, max_length=40)
    target_entity_id: UUID | None = None
    field_changes: list[FieldChange] = Field(default_factory=list)
    rationale: str = Field(min_length=10, max_length=4000)
    evidence: str | None = Field(default=None, max_length=4000)
