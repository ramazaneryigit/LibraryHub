"""Tenant Data Plane models (schema ``tenant``).

Architecture v2 §1.2 and §3. Aşama 3 builds the *skeleton* only: the tables,
the isolation policies and the roles. No data is moved here -- mapping the
existing `public.items` rows onto holdings is Aşama 4.

The boundary this schema enforces
---------------------------------
    GLOBAL (public)                      TENANT (tenant)
    Work -> Expression -> Manifestation   Holding -> Item
                                          Location

A Manifestation is defined once, globally, and shared by every institution. A
Holding is one institution's statement about that Manifestation (call number,
collection, serial volume range, licence). An Item is one physical or digital
copy inside a Holding, and is the level at which a barcode exists.

Why an Item is not a global Entity
----------------------------------
`public.items` currently is: it is a subtype row of `public.entities`. At 100M
items the global identity registry would be dominated by one library's physical
copies, and `entity_relation` would be able to point at a barcode. Items are
inherently institutional, so they live here and own their own identifiers.

Cross-plane foreign keys and `ddl_if`
-------------------------------------
`branch_id`, `manifestation_entity_id` and `expression_entity_id` point at the
Control Plane and the Global Knowledge Plane, so they are cross-schema (and, in
the test suite, cross-database). SQLite cannot parse a qualified REFERENCES
clause at all -- `REFERENCES control.branches (id)` fails with `near ".":
syntax error` -- so those three constraints carry
`.ddl_if(dialect="postgresql")` and exist on PostgreSQL only. The same-schema
`items -> holdings` and `items -> locations` constraints have no such problem
and are enforced everywhere.

That is also the honest architectural position: cross-plane foreign keys are a
single-cluster convenience. D5 requires that a tenant can move to another
cluster, and the moment a plane is split these constraints have to go. See
docs/architecture-v2.md §5.3 and §18.

See docs/architecture-v2.md §3.3 for the DDL this implements.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .ids import uuid7

TENANT_SCHEMA = "tenant"
CONTROL_SCHEMA = "control"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantLocation(Base):
    """A shelving location inside a branch.

    Tenant-scoped even though it belongs to a branch: `branch_id` is the
    Control Plane's record, `tenant_id` is the isolation key every tenant table
    carries and the leading column of every tenant index.
    """

    __tablename__ = "locations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["branch_id"],
            [f"{CONTROL_SCHEMA}.branches.id"],
            name="fk_locations_branch",
            ondelete="RESTRICT",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "location_type IS NULL OR location_type IN "
            "('shelf', 'room', 'closed_stack', 'offsite', 'reading_room')",
            name="ck_locations_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "branch_id",
            "code",
            name="uq_locations_tenant_branch_code",
        ),
        {"schema": TENANT_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    location_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class TenantHolding(Base):
    """One institution's collection statement about a Manifestation.

    Holding exists as a first-class row rather than as columns on Item because
    three real cases cannot be modelled otherwise:

    * **Serials.** "vol. 12-18, 1998-2004, no. 14 missing" is a statement about
      a run, not about a copy. Items are the individual issues beneath it.
    * **Electronic resources.** A subscription has a URL and a licence and no
      barcode, shelfmark or copy at all; a mandatory Item would force a fake one.
    * **Call number policy.** Libraries assign call numbers per collection, so
      the three copies of a work usually share one.

    The target is an exclusive arc: exactly one of `manifestation_entity_id` or
    `expression_entity_id` is set. The check is written portably --
    `num_nonnulls(...)` is PostgreSQL-only and would break the SQLite test
    engine -- and SQLite enforces it too.
    """

    __tablename__ = "holdings"

    __table_args__ = (
        ForeignKeyConstraint(
            ["branch_id"],
            [f"{CONTROL_SCHEMA}.branches.id"],
            name="fk_holdings_branch",
            ondelete="RESTRICT",
        ).ddl_if(dialect="postgresql"),
        ForeignKeyConstraint(
            ["manifestation_entity_id"],
            ["manifestations.entity_id"],
            name="fk_holdings_manifestation",
            ondelete="RESTRICT",
        ).ddl_if(dialect="postgresql"),
        ForeignKeyConstraint(
            ["expression_entity_id"],
            ["expressions.entity_id"],
            name="fk_holdings_expression",
            ondelete="RESTRICT",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "(manifestation_entity_id IS NULL) "
            "<> (expression_entity_id IS NULL)",
            name="ck_holdings_target_exactly_one",
        ),
        CheckConstraint(
            "holding_type IN ('physical', 'electronic', 'microform', 'other')",
            name="ck_holdings_type",
        ),
        CheckConstraint(
            "status IN ('active', 'closed', 'suppressed')",
            name="ck_holdings_status",
        ),
        # Idempotent import key. Not (branch, manifestation) alone, because a
        # branch legitimately holds the same Manifestation in several
        # collections (reference, circulating, serial archive).
        UniqueConstraint(
            "branch_id",
            "manifestation_entity_id",
            "local_holding_key",
            name="uq_holdings_branch_manifestation_key",
        ),
        Index(
            "ix_holdings_tenant_manifestation",
            "tenant_id",
            "manifestation_entity_id",
        ),
        # "Which institutions hold this Manifestation?" -- the global -> tenant
        # direction, which the API will need for holdings-aware discovery.
        Index(
            "ix_holdings_manifestation",
            "manifestation_entity_id",
        ),
        {"schema": TENANT_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    # Mandatory (OD4). Aşama 2 gave every organization a default branch, so
    # single-branch institutions are already covered and this never needs a
    # nullable-then-backfill migration.
    branch_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    manifestation_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    expression_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    holding_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="physical",
    )

    collection_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    call_number: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    call_number_scheme: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Serials: free-text run statement, e.g. "c.12-18 (1998-2004), 14 eksik".
    holding_statement: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    enumeration_pattern: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    access_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    license_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    acquisition_source: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    public_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    staff_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    local_holding_key: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class TenantItem(Base):
    """A single physical or digital copy inside a Holding.

    `availability_status` is a cache, not the source of truth. Today it is the
    only place circulation state lives; once loan and reservation tables exist
    they become authoritative and this column is derived from them, otherwise
    the two disagree the first time a book is borrowed
    (docs/architecture-v2.md §3.3, D2.2).

    `barcode` is unique per tenant (OD3), not per branch: a copy transferred
    between branches must not be able to collide with another copy's barcode.
    """

    __tablename__ = "items"

    __table_args__ = (
        ForeignKeyConstraint(
            ["holding_id"],
            [f"{TENANT_SCHEMA}.holdings.id"],
            name="fk_items_holding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["location_id"],
            [f"{TENANT_SCHEMA}.locations.id"],
            name="fk_items_location",
            ondelete="SET NULL",
        ),
        # NULL barcodes stay allowed: both PostgreSQL and SQLite treat NULLs as
        # distinct in a unique constraint, so uncatalogued copies do not clash.
        UniqueConstraint(
            "tenant_id",
            "barcode",
            name="uq_items_tenant_barcode",
        ),
        # Set only on rows migrated from the legacy global `public.items`
        # table. It records where the row came from and lets the compatibility
        # view hand back the identifier that existing API clients already hold.
        # Items created directly in the tenant plane leave it NULL and are
        # identified by `id`.
        UniqueConstraint(
            "legacy_entity_id",
            name="uq_items_legacy_entity_id",
        ),
        CheckConstraint(
            "lifecycle_status IN "
            "('active', 'withdrawn', 'lost', 'missing', 'in_repair')",
            name="ck_items_lifecycle_status",
        ),
        Index("ix_items_holding", "holding_id"),
        {"schema": TENANT_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    holding_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    legacy_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    barcode: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    accession_number: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    item_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    location_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    shelfmark: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    condition: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    availability_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unknown",
    )

    circulation_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
    )

    price_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    price_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    acquired_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    donor: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
    )

    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
