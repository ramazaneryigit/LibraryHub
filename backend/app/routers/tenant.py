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

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..control_models import User
from ..dependencies import current_user, tenant_db
from ..ids import uuid7


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
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Girilen değer izin verilen değerlerden biri değil.",
    ),
    "23503": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Başvurulan kayıt bulunamadı.",
    ),
    "23502": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
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

    return HTTPException(
        status_code=status_code,
        detail=f"{message} ({constraint})" if constraint else message,
    )


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
        {"id": branch_id, "tenant_id": user.tenant_id},
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
        {"id": holding_id},
    ).scalar()

    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding bulunamadı.",
        )


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
                h.call_number
            FROM tenant.items i
            JOIN tenant.holdings h ON h.id = i.holding_id
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
            values,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _translate(exc) from exc

    row = db.execute(
        text(f"SELECT {select_columns} FROM {table} WHERE id = :id"),
        {"id": values["id"]},
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Değiştirilecek alan gönderilmedi.",
        )

    assignments = ", ".join(f"{name} = :{name}" for name in changes)

    try:
        result = db.execute(
            text(
                f"UPDATE {table} SET {assignments}, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {
                **changes,
                "id": record_id,
                "updated_at": datetime.now(timezone.utc),
            },
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
        {"id": record_id},
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
