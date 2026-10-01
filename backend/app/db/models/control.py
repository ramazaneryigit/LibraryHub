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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utcnow
from ...core.ids import uuid7

__all__ = [
    "Branch",
    "EmailVerification",
    "Organization",
    "OrganizationDomain",
    "Tenant",
    "TenantDatabase",
    "User",
    "UserSession",
]

CONTROL_SCHEMA = "control"


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
    """A staff account, belonging to at most one tenant.

    ``tenant_id`` is what makes the rest of the system work: it is the value
    bound into `libraryhub.tenant_id` for every request this user makes, and the
    row level security policies on `tenant.*` do the isolation from there. A
    user is therefore never asked which library they are acting for -- guessing
    it, or accepting it from the client, would be the whole vulnerability.

    It is nullable for one reason: a **platform administrator** curates the shared
    record rather than a library. They review the proposals tenants raise, merge
    identities, and load batches -- work that belongs to no institution, and
    giving them a tenant would mean inventing one. `tenant_db` refuses them with a
    403 instead of binding a tenant they do not have.

    The database keeps the two apart: a user with no tenant must be an `admin`,
    because a librarian with no library cannot act at all.

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
        CheckConstraint(
            "account_kind IN ('institutional', 'corporate')",
            name="ck_users_account_kind",
        ),
        # Read as: only a library's own staff must belong to a library. An
        # academician, a publisher, the ISBN agency or a vendor is tenant-less by
        # nature.
        #
        # The `role = 'admin'` escape is a transition, not a design. Before this
        # revision the rule was "a tenant-less account is an administrator", and
        # every existing creation path -- and the tests -- rely on it. A
        # tenant-less administrator should be `principal_kind = 'platform'`, and
        # a constraint cannot infer that from a missing value, so the honest move
        # is to keep accepting the old shape while the creation paths are
        # corrected, rather than to relax it silently or break them.
        CheckConstraint(
            "tenant_id IS NOT NULL OR principal_kind <> 'tenant_staff' "
            "OR role = 'admin'",
            name="ck_users_tenant_required",
        ),
        CheckConstraint(
            "principal_kind IN ('platform', 'tenant_staff', 'academician', "
            "'publisher', 'isbn_agency', 'vendor')",
            name="ck_users_principal_kind",
        ),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_subject_entity", "subject_entity_id"),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
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

    # `institutional` (a university or library on an academic domain) or
    # `corporate` (a publisher or other organization on a domain that had to be
    # claimed and verified for it). Decided by `email_domains.classify_email`,
    # never by the client. See docs/architecture-v2.md §0.14.
    account_kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="institutional",
    )

    # Which of the five participants this account is. `role` says what a person
    # may do *inside* a library; `principal_kind` says what kind of participant
    # they are at all, and therefore whether they belong to a library.
    #
    # The platform is the only one that exists today; the other four are declared
    # so the identity model stops forbidding them, and they gain workspaces in a
    # later step. See docs/merkezi-yapi-plani.md §3.
    principal_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="tenant_staff",
        # A plain string, so SQLite accepts it too -- unlike the PostgreSQL-only
        # expressions that broke `outbox_events`. Raw SQL inserts do not run
        # Python-side defaults, and the tests create accounts that way.
        server_default="tenant_staff",
    )

    # The authority record this account speaks for: a publisher account points at
    # its `collective_agents` row, an academician account at its `persons` row.
    # Null for library staff and the platform, who act for a tenant instead.
    #
    # Without it "which titles are mine" is unanswerable, and answering it from a
    # display name would make a spelling mistake into a different publisher.
    subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )

    # NULL means the address has never been shown to receive mail, and such an
    # account cannot log in. `create_user.py`, which runs with the owner
    # credential, may set this at creation. The panel may not:
    # `guard_application_account_writes` refuses an application role an account
    # that is already verified, so one opened over the API is confirmed by its
    # holder. See docs/architecture-v2.md §0.22.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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


class OrganizationDomain(Base):
    """A corporate domain that has been claimed for an organization.

    This is what makes "kurumsal mail adres doğrulaması" mean something. An
    address on an academic domain proves affiliation by itself; an address on
    `@yayinevi.com.tr` proves nothing, because anybody can register a domain.
    The domain therefore has to be attached to an organization here -- by an
    administrator, with the method recorded -- before an account on it is
    accepted.

    `verification_method` records *how* the claim was established (a DNS record,
    a message to a role address, a signed letter), because "verified" without
    the how is not auditable later.
    """

    __tablename__ = "organization_domains"

    __table_args__ = (
        UniqueConstraint("domain", name="uq_organization_domains_domain"),
        Index(
            "ix_organization_domains_organization_id",
            "organization_id",
        ),
        {"schema": CONTROL_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )

    domain: Mapped[str] = mapped_column(
        String(253),
        nullable=False,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            f"{CONTROL_SCHEMA}.organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    verification_method: Mapped[str | None] = mapped_column(
        String(50),
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


class EmailVerification(Base):
    """A pending "prove you can receive at this address" challenge.

    The account row is created immediately, already carrying its tenant and its
    `account_kind`, but with `email_verified_at` NULL -- so it exists, and cannot
    be logged into. Doing it this way means `uq_users_email` holds the address
    from the first request, and verification is a single UPDATE rather than a
    second insert that could fail after the token was already spent.

    The raw token is never stored, exactly as with sessions. The API has no mail
    sender yet, so the link is written to the application log -- the same thing
    a development mailer does -- and `scripts/verify_email.py` can complete a
    challenge from the console. See docs/architecture-v2.md §0.14.
    """

    __tablename__ = "email_verifications"

    __table_args__ = (
        UniqueConstraint(
            "token_hash",
            name="uq_email_verifications_token_hash",
        ),
        Index("ix_email_verifications_user_id", "user_id"),
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

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
