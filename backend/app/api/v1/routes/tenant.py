"""Tenant-scoped endpoints.

These exist to prove the isolation chain end to end, and to give Aşama 5 a
working pattern to extend:

    bearer token -> user -> tenant_id -> SET LOCAL libraryhub.tenant_id
                 -> row level security policy -> only that tenant's rows

Every query here is deliberately missing a `WHERE tenant_id = ...`. That is the
demonstration: the session from `tenant_db` has already bound the tenant, and the
policy on `tenant.*` decides what exists. Forgetting the binding yields an empty
answer, never somebody else's data.

See docs/architecture-v2.md §5.2 and §0.13.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.types import JSON

from ....db.models import User
from ...deps import current_user, tenant_db
from ....core.ids import uuid7
from ....schemas.tenant import HoldingCreate, HoldingUpdate, ItemCreate, ItemUpdate, FieldChange, ProposalCreate


router = APIRouter(
    prefix="/tenant",
    tags=["tenant"],
)


logger = logging.getLogger("libraryhub.tenant")


# SQLSTATE values, turned into answers a person can act on. The constraints are
# not re-declared as Pydantic enums on purpose: two copies of the same rule drift
# apart, and the database is the one that is right.
_CONSTRAINT_RESPONSES = {
    "23505": (
        status.HTTP_409_CONFLICT,
        "Bu kayıt zaten var (tekrar eden bir alan).",
    ),
    "23514": (
        # Literal rather than `status.HTTP_422_UNPROCESSABLE_ENTITY`, which
        # Starlette has renamed; the number is the same either way and does not
        # depend on which version is installed.
        422,
        "Girilen değer izin verilen değerlerden biri değil.",
    ),
    "23503": (
        422,
        "Başvurulan kayıt bulunamadı.",
    ),
    "23502": (
        422,
        "Zorunlu bir alan boş bırakılmış.",
    ),
}


def _sqlstate(origin) -> str | None:
    """The SQLSTATE of a driver error.

    psycopg3 exposes `sqlstate`; psycopg2 exposed `pgcode`. Both are read, because
    a lookup that quietly stops matching does not fail -- it falls through to a
    generic message and looks like a bug somewhere else entirely, which is
    exactly what happened the first time this was written.
    """

    return getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None)


def _translate(exc: IntegrityError) -> HTTPException:
    origin = getattr(exc, "orig", None)
    code = _sqlstate(origin)
    constraint = getattr(getattr(origin, "diag", None), "constraint_name", None)
    primary = getattr(getattr(origin, "diag", None), "message_primary", None)

    # An error reduced to a friendly sentence still has to be diagnosable.
    logger.warning(
        "constraint violation: sqlstate=%s constraint=%s | %s",
        code,
        constraint,
        origin,
    )

    response = _CONSTRAINT_RESPONSES.get(code)

    if response is None:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kayıt yazılamadı.",
        )

    status_code, message = response

    if constraint:
        detail = f"{message} ({constraint})"
    elif primary:
        # A trigger raises without a constraint name, and its message is the only
        # useful part -- without this the branch guard would report "not one of
        # the allowed values", which is both wrong and unactionable.
        detail = f"{message} {primary}"
    else:
        detail = message

    return HTTPException(status_code=status_code, detail=detail)


def _proposal_view(row) -> dict:
    """Normalise a proposal row for JSON output.

    PostgreSQL hands a `json` column back already parsed; SQLite returns the text
    it stored, because `text()` carries no type information for the driver to
    work from. Both are accepted here so the response shape does not depend on
    which engine answered.
    """

    result = _jsonable(row)

    for name in ("field_changes", "applied_fields"):
        value = result.get(name)

        if isinstance(value, str):
            try:
                result[name] = json.loads(value)
            except json.JSONDecodeError:
                result[name] = []

        elif value is None and name == "field_changes":
            result[name] = []

    return result


def _bindable(values: dict) -> dict:
    """UUIDs to their canonical strings before binding.

    These paths use `text()`, which carries no type information, so the driver
    decides what to do with a `uuid.UUID`: psycopg3 adapts it and sqlite3 refuses
    it with "type 'UUID' is not supported". Sending the canonical string is
    accepted by both, which is what lets the SQLite suite exercise the write
    paths at all -- they were unreachable from a test before this, and a write
    path nothing tests is a write path nobody has checked.
    """

    return {
        name: str(value) if isinstance(value, UUID) else value
        for name, value in values.items()
    }


def _assert_branch_is_ours(db: Session, user: User, branch_id: UUID) -> None:
    """Check the branch belongs to the caller's tenant.

    `control.branches` carries no row level security, so `fk_holdings_branch`
    would happily accept another institution's branch id -- a foreign key checks
    that the row exists, not that it is yours. Until the control plane has
    policies of its own, this check is the only thing standing there, which is
    exactly the kind of gap that should be written down rather than assumed
    away. See docs/architecture-v2.md §0.14.
    """

    found = db.execute(
        text(
            "SELECT 1 FROM control.branches "
            "WHERE id = :id AND tenant_id = :tenant_id"
        ),
        _bindable({"id": branch_id, "tenant_id": user.tenant_id}),
    ).scalar()

    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Şube bulunamadı.",
        )


def _jsonable(row) -> dict:
    """Row to a JSON-safe dict.

    Raw SQL is used deliberately on these paths -- the absence of a
    `WHERE tenant_id = ...` is the point, so hiding the statement behind an ORM
    would hide the thing worth seeing -- and that means dates and UUIDs come
    back as objects.
    """

    result = {}

    for key, value in row.items():
        if isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)

        result[key] = value

    return result


def _assert_holding_is_ours(db: Session, holding_id: UUID) -> None:
    """Check a holding is the caller's before hanging an item off it.

    `fk_items_holding` cannot do this: a foreign key check runs outside row
    level security, so it confirms the holding exists and not that it is yours.
    Without this, an institution could attach a copy to another institution's
    holding and the row would pass every constraint.

    Both "not yours" and "does not exist" answer 404, so the endpoint cannot be
    used to probe for other institutions' records.
    """

    found = db.execute(
        text("SELECT 1 FROM tenant.holdings WHERE id = :id"),
        _bindable({"id": holding_id}),
    ).scalar()

    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding bulunamadı.",
        )


@router.get("/me")
def whoami(
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    """Who the caller is, and which library they are acting for.

    A tenant workspace opens with this: a librarian should see their own
    institution's name before anything else, and the account they are signed in
    as. The tenant comes from the session, never from the request -- the same
    rule as every other route here.
    """

    tenant = db.execute(
        text("select display_name, slug from control.tenants where id = :id"),
        {"id": user.tenant_id},
    ).mappings().first()

    # The institution is reached through the caller's *branch*, not by asking
    # `control.organizations` directly. `branches` carries the same fail-closed
    # policy as the tenant tables (§0.15) so this returns the caller's own
    # organization; `organizations` has no policy at all, and the first version
    # of this function read it directly and reported whichever organization
    # sorted first -- somebody else's.
    organization = db.execute(
        text(
            "select o.name from control.branches b "
            "join control.organizations o on o.id = b.organization_id "
            "order by b.is_default desc, b.name limit 1"
        )
    ).scalar()

    return {
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": str(user.tenant_id),
        "tenant_name": tenant["display_name"] if tenant else None,
        "tenant_slug": tenant["slug"] if tenant else None,
        "organization_name": organization,
    }


@router.get("/summary")
def summary(
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    """The numbers a librarian wants on arrival.

    Every one of them is scoped by the policies rather than by a `WHERE`: this
    runs inside `tenant_session`, so the counts are of the caller's own library
    whether or not this function remembers to say so.
    """

    row = db.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM tenant.holdings) AS holdings,
                (SELECT count(*) FROM tenant.holdings
                  WHERE status <> 'suppressed') AS published_holdings,
                (SELECT count(*) FROM tenant.items) AS items,
                (SELECT count(*) FROM tenant.items
                  WHERE availability_status = 'available') AS available,
                (SELECT count(*) FROM tenant.items
                  WHERE availability_status = 'on_loan') AS on_loan,
                (SELECT count(*) FROM control.branches) AS branches,
                (SELECT count(*) FROM tenant.change_proposals) AS proposals,
                (SELECT count(*) FROM tenant.change_proposals
                  WHERE status = 'pending') AS pending_proposals
            """
        )
    ).mappings().one()

    return {
        "tenant_id": str(user.tenant_id),
        "holdings": row["holdings"],
        "published_holdings": row["published_holdings"],
        "items": row["items"],
        "available": row["available"],
        "on_loan": row["on_loan"],
        "branches": row["branches"],
        "proposals": row["proposals"],
        "pending_proposals": row["pending_proposals"],
    }


@router.get("/branches")
def list_branches(
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    """The caller's branches, default first.

    No `WHERE tenant_id` here either. `control.branches` gained the same
    fail-closed policy as the tenant tables in §0.15, so an application session
    with no tenant bound sees nothing at all -- which is what makes a
    branch-picking endpoint safe to write without a filter.
    """

    rows = db.execute(
        text(
            """
            SELECT id, organization_id, code, name, is_default
            FROM control.branches
            ORDER BY is_default DESC, name
            """
        )
    ).mappings().all()

    return {
        "tenant_id": str(user.tenant_id),
        "count": len(rows),
        "branches": [_jsonable(row) for row in rows],
    }


@router.get("/items")
def list_items(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    rows = db.execute(
        text(
            """
            SELECT
                i.id,
                i.barcode,
                i.shelfmark,
                i.availability_status,
                i.lifecycle_status,
                h.holding_type,
                h.call_number,
                b.name AS branch_name,
                o.name AS organization_name
            FROM tenant.items i
            JOIN tenant.holdings h ON h.id = i.holding_id
            LEFT JOIN control.branches b ON b.id = h.branch_id
            LEFT JOIN control.organizations o ON o.id = b.organization_id
            ORDER BY i.barcode NULLS LAST, i.id
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    return {
        "tenant_id": str(user.tenant_id),
        "count": len(rows),
        "items": [
            {
                "id": str(row["id"]),
                "barcode": row["barcode"],
                "shelfmark": row["shelfmark"],
                "availability_status": row["availability_status"],
                "lifecycle_status": row["lifecycle_status"],
                "holding_type": row["holding_type"],
                "call_number": row["call_number"],
                # Custody, derived from the structure rather than read from a
                # relation table: item -> holding -> branch -> organization.
                "branch_name": row["branch_name"],
                "organization_name": row["organization_name"],
            }
            for row in rows
        ],
    }


@router.get("/holdings")
def list_holdings(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    rows = db.execute(
        text(
            """
            SELECT
                h.id,
                h.holding_type,
                h.call_number,
                h.local_holding_key,
                h.status,
                h.manifestation_entity_id,
                h.expression_entity_id,
                COUNT(i.id) AS item_count
            FROM tenant.holdings h
            LEFT JOIN tenant.items i ON i.holding_id = h.id
            GROUP BY h.id
            ORDER BY h.local_holding_key
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    return {
        "tenant_id": str(user.tenant_id),
        "count": len(rows),
        "holdings": [
            {
                "id": str(row["id"]),
                "holding_type": row["holding_type"],
                "call_number": row["call_number"],
                "local_holding_key": row["local_holding_key"],
                "status": row["status"],
                "manifestation_entity_id": (
                    str(row["manifestation_entity_id"])
                    if row["manifestation_entity_id"]
                    else None
                ),
                "expression_entity_id": (
                    str(row["expression_entity_id"])
                    if row["expression_entity_id"]
                    else None
                ),
                "item_count": row["item_count"],
            }
            for row in rows
        ],
    }


# --------------------------------------------------------------------- writes
#
# Everything below writes to the tenant plane only. `tenant_db` has dropped the
# transaction to `libraryhub_tenant_app`, which holds no INSERT or UPDATE
# privilege on `public`, so a mistake here cannot reach the shared bibliographic
# record -- PostgreSQL refuses it.
#
# That is what "kendi verilerini yapımızı bozmadan" means in practice: not a
# convention somebody has to remember, a grant. Changing a Work, an Expression or
# a Manifestation is deliberately not possible from here; it will go through a
# proposal that an administrator reviews. See docs/architecture-v2.md §0.14.


HOLDING_FIELDS = (
    "branch_id",
    "manifestation_entity_id",
    "expression_entity_id",
    "holding_type",
    "collection_code",
    "call_number",
    "call_number_scheme",
    "holding_statement",
    "enumeration_pattern",
    "access_url",
    "license_note",
    "acquisition_source",
    "public_note",
    "staff_note",
    "local_holding_key",
    "status",
)

HOLDING_SELECT = (
    "id, tenant_id, branch_id, manifestation_entity_id, expression_entity_id, "
    "holding_type, collection_code, call_number, call_number_scheme, "
    "holding_statement, enumeration_pattern, access_url, license_note, "
    "acquisition_source, public_note, staff_note, local_holding_key, status, "
    "created_at, updated_at"
)

ITEM_FIELDS = (
    "holding_id",
    "barcode",
    "accession_number",
    "item_type",
    "shelfmark",
    "condition",
    "availability_status",
    "notes",
    "donor",
    "lifecycle_status",
)

ITEM_SELECT = (
    "id, tenant_id, holding_id, barcode, accession_number, item_type, "
    "location_id, shelfmark, condition, availability_status, price_amount, "
    "price_currency, acquired_at, donor, notes, lifecycle_status, "
    "created_at, updated_at"
)


def _insert(
    db: Session,
    table: str,
    fields: tuple,
    payload,
    tenant_id: UUID,
    select_columns: str,
) -> dict:
    values = {name: getattr(payload, name) for name in fields}
    values["id"] = uuid7()
    values["tenant_id"] = tenant_id
    values["created_at"] = datetime.now(timezone.utc)
    values["updated_at"] = values["created_at"]

    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)

    try:
        db.execute(
            text(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            ),
            _bindable(values),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _translate(exc) from exc

    row = db.execute(
        text(f"SELECT {select_columns} FROM {table} WHERE id = :id"),
        _bindable({"id": values["id"]}),
    ).mappings().one()

    return _jsonable(row)


def _update(
    db: Session,
    table: str,
    fields: tuple,
    record_id: UUID,
    payload,
    select_columns: str,
) -> dict:
    changes = {
        name: value
        for name, value in payload.model_dump(exclude_unset=True).items()
        if name in fields
    }

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Değiştirilecek alan gönderilmedi.",
        )

    assignments = ", ".join(f"{name} = :{name}" for name in changes)

    try:
        result = db.execute(
            text(
                f"UPDATE {table} SET {assignments}, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            _bindable(
                {
                    **changes,
                    "id": record_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            ),
        )

        if result.rowcount == 0:
            # Row level security has already hidden any other institution's row,
            # so this is "not yours" or "does not exist" and the two are
            # deliberately indistinguishable.
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kayıt bulunamadı.",
            )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _translate(exc) from exc

    row = db.execute(
        text(f"SELECT {select_columns} FROM {table} WHERE id = :id"),
        _bindable({"id": record_id}),
    ).mappings().one()

    return _jsonable(row)


@router.post("/holdings", status_code=status.HTTP_201_CREATED)
def create_holding(
    payload: HoldingCreate,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    _assert_branch_is_ours(db, user, payload.branch_id)

    return _insert(
        db,
        "tenant.holdings",
        HOLDING_FIELDS,
        payload,
        user.tenant_id,
        HOLDING_SELECT,
    )


@router.patch("/holdings/{holding_id}")
def update_holding(
    holding_id: UUID,
    payload: HoldingUpdate,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    return _update(
        db,
        "tenant.holdings",
        HOLDING_FIELDS,
        holding_id,
        payload,
        HOLDING_SELECT,
    )


@router.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemCreate,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    _assert_holding_is_ours(db, payload.holding_id)

    return _insert(
        db,
        "tenant.items",
        ITEM_FIELDS,
        payload,
        user.tenant_id,
        ITEM_SELECT,
    )


@router.patch("/items/{item_id}")
def update_item(
    item_id: UUID,
    payload: ItemUpdate,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    return _update(
        db,
        "tenant.items",
        ITEM_FIELDS,
        item_id,
        payload,
        ITEM_SELECT,
    )


# ------------------------------------------------------------------ proposals
#
# The tenant cannot write the global plane -- PostgreSQL refuses it -- and that
# is the point. This is how an institution says that something on a shared
# record is wrong, or that a record is missing entirely. It is a request, not an
# edit: accepting one writes nothing, and applying is a separate step with a
# whitelist, because "the database accepted this JSON" is not the same claim as
# "this is a valid value for publication_date".
#
# See docs/architecture-v2.md §0.16.


PROPOSAL_SELECT = (
    "id, tenant_id, submitted_by, submitted_by_email, change_type, "
    "target_entity_type, target_entity_id, field_changes, rationale, evidence, "
    "status, reviewed_by, reviewed_at, review_note, applied_at, applied_fields, "
    "created_at, updated_at"
)

# `field_changes` is a JSON column and this router talks in raw SQL, so the
# parameter is typed explicitly. Without it the driver sees a Python list and
# offers it as an array, which the column will not take.
PROPOSAL_INSERT = text(
    """
    INSERT INTO tenant.change_proposals
        (id, tenant_id, submitted_by, submitted_by_email, change_type,
         target_entity_type, target_entity_id, field_changes, rationale,
         evidence, status, created_at, updated_at)
    VALUES
        (:id, :tenant_id, :submitted_by, :submitted_by_email, :change_type,
         :target_entity_type, :target_entity_id, :field_changes, :rationale,
         :evidence, :status, :created_at, :updated_at)
    """
).bindparams(bindparam("field_changes", type_=JSON))


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(
    payload: ProposalCreate,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    now = datetime.now(timezone.utc)

    values = {
        "id": uuid7(),
        # From the account, never from the request.
        "tenant_id": user.tenant_id,
        "submitted_by": user.id,
        "submitted_by_email": user.email,
        "change_type": payload.change_type,
        "target_entity_type": payload.target_entity_type,
        "target_entity_id": payload.target_entity_id,
        "field_changes": [
            change.model_dump() for change in payload.field_changes
        ],
        "rationale": payload.rationale.strip(),
        "evidence": (payload.evidence or "").strip() or None,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }

    try:
        db.execute(PROPOSAL_INSERT, _bindable(values))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _translate(exc) from exc

    row = db.execute(
        text(
            f"SELECT {PROPOSAL_SELECT} FROM tenant.change_proposals "
            "WHERE id = :id"
        ),
        _bindable({"id": values["id"]}),
    ).mappings().one()

    return _proposal_view(row)


@router.get("/proposals")
def list_proposals(
    proposal_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    # No `WHERE tenant_id` here either. The policy decides, so a mistake in this
    # function shows one institution's proposals to another only if the policy is
    # wrong -- which is the place to be wrong, once, rather than here, repeatedly.
    query = f"SELECT {PROPOSAL_SELECT} FROM tenant.change_proposals"
    params: dict = {"limit": limit}

    if proposal_status:
        query += " WHERE status = :status"
        params["status"] = proposal_status

    query += " ORDER BY created_at DESC LIMIT :limit"

    rows = db.execute(text(query), params).mappings().all()

    return {
        "tenant_id": str(user.tenant_id),
        "count": len(rows),
        "proposals": [_proposal_view(row) for row in rows],
    }


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: UUID,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    row = db.execute(
        text(
            f"SELECT {PROPOSAL_SELECT} FROM tenant.change_proposals "
            "WHERE id = :id"
        ),
        _bindable({"id": proposal_id}),
    ).mappings().first()

    if row is None:
        # Another institution's proposal is invisible rather than forbidden, so
        # the endpoint cannot be used to probe for their existence.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Öneri bulunamadı.",
        )

    return _proposal_view(row)


@router.post("/proposals/{proposal_id}/withdraw")
def withdraw_proposal(
    proposal_id: UUID,
    db: Session = Depends(tenant_db),
    user: User = Depends(current_user),
):
    """Withdraw a proposal that has not been decided yet.

    A proposal that has been accepted, rejected or already applied is a record of
    a decision, so it does not move back to `pending` -- the row count says so and
    the answer is 404 rather than a silent no-op.
    """

    result = db.execute(
        text(
            "UPDATE tenant.change_proposals "
            "SET status = 'withdrawn', updated_at = :updated_at "
            "WHERE id = :id AND status = 'pending'"
        ),
        _bindable(
            {"id": proposal_id, "updated_at": datetime.now(timezone.utc)}
        ),
    )

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geri çekilebilecek bekleyen bir öneri bulunamadı.",
        )

    db.commit()

    row = db.execute(
        text(
            f"SELECT {PROPOSAL_SELECT} FROM tenant.change_proposals "
            "WHERE id = :id"
        ),
        _bindable({"id": proposal_id}),
    ).mappings().one()

    return _proposal_view(row)