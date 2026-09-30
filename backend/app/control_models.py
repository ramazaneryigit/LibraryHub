"""Control Plane models (schema ``control``).

Architecture v2 §1.2: the Control Plane holds *who the tenants are* —
identity, tenancy boundaries, routing and (later) authentication and
subscription. It is deliberately separate from the Global Knowledge Plane
(``public``, bibliographic/authority data) and the Tenant Data Plane
(``tenant``, holdings/items/patrons).

Decision D14 is the reason ``organizations`` and ``collective_agents`` are two
records linked by a foreign key rather than one row:

* ``public.collective_agents`` is the citable *authority* record. A university
  library is a corporate body that can be a publisher, a corporate author or a
  holding institution, and that citation must survive forever.
* ``control.organizations`` is the *tenant-facing* record: it can be suspended,
  renamed, or moved to another cluster.

Merging them would mean suspending a tenant damages a citation. They are also
not the same set: not every corporate body is a tenant (publishers are not),
and not every tenant is a corporate body.

See docs/architecture-v2.md §1.2, §3.3 and §5.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .ids import uuid7

CONTROL_SCHEMA = "control"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """The isolation and billing boundary.

    ``cluster_id`` records which physical PostgreSQL cluster currently holds
    this tenant's data. The application reads it through the routing layer and
    never hardcodes a database location, so a tenant can be moved to another
    cluster without a code change (docs/architecture-v2.md §5.3).
    """

    __tablename__ = "tenants"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_tenants_status",
        ),
        UniqueConstraint("slug", name="uq_tenants_slug"),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    slug: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    display_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
    )

    cluster_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="primary",
    )

    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    data_residency: Mapped[str | None] = mapped_column(
        String(100),
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


class Organization(Base):
    """An institution that subscribes to LibraryHub.

    ``tenant_id`` is unique: this draft models one tenant per subscribing
    institution. A consortium tenant with several member libraries would need
    that constraint relaxed, which is a trivial ``DROP CONSTRAINT``; adding it
    later would require backfilling, so the stricter form is the safer default
    (docs/architecture-v2.md §3.3).
    """

    __tablename__ = "organizations"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_organizations_tenant"),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # Link to the global authority record. Nullable because an organization can
    # exist before its corporate-body record does, and SET NULL because losing
    # the authority record must not delete the tenant.
    collective_agent_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "collective_agents.entity_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    org_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    isil: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class Branch(Base):
    """A service point inside an organization.

    Kept even for single-branch institutions: making ``holdings.branch_id``
    mandatory later is far easier if every organization already has a default
    branch, and it avoids a nullable-then-not-null migration.
    """

    __tablename__ = "branches"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "code",
            name="uq_branches_tenant_code",
        ),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.organizations.id",
            ondelete="CASCADE",
        ),
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

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class TenantDatabase(Base):
    """Where a tenant's data physically lives, resolved at runtime.

    ``dsn_secret_ref`` stores a *reference* to a secret, never the password
    itself: this table is read by the routing layer and must stay safe to
    query and to dump.
    """

    __tablename__ = "tenant_databases"

    __table_args__ = (
        {"schema": CONTROL_SCHEMA},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.tenants.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    cluster_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    dsn_secret_ref: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    read_replica_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class User(Base):
    """A staff account, belonging to exactly one tenant.

    ``tenant_id`` is what makes the rest of the system work: it is the value
    bound into `libraryhub.tenant_id` for every request this user makes, and the
    row level security policies on `tenant.*` do the isolation from there. A
    user is therefore never asked which library they are acting for -- guessing
    it, or accepting it from the client, would be the whole vulnerability.

    ``email`` is globally unique rather than unique per tenant: login takes an
    email and nothing else, so two tenants sharing an address would make it
    ambiguous.
    """

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'librarian', 'viewer')",
            name="ck_users_role",
        ),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_tenant_id", "tenant_id"),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )

    display_name: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="librarian",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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


class UserSession(Base):
    """A server-side session.

    Named `UserSession` and not `Session` on purpose: `Session` is SQLAlchemy's
    own name, and a module-level collision of exactly that kind already caused a
    silent bug once in this project (docs/architecture-v2.md §0.9).

    Only the SHA-256 of the token is stored, so the table is safe to read and to
    dump. Rows are revoked rather than deleted, which keeps "this session was
    ended" answerable after the fact.
    """

    __tablename__ = "sessions"

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        Index("ix_sessions_user_id", "user_id"),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
