"""Field assertions: the endpoint a participant files a claim through.

Two audiences, one resource, so one module and one router with explicit paths
rather than a prefix that would have to be chosen for both.

A library files and reads its own claims. A curator reads the queue and decides.
The split is not stylistic: filing goes through the application role, where the
trigger in migration `a4c7e2b91f38` refuses a claim filed as somebody else's
source, and deciding goes through the owner credential, which is the same
privilege the proposal queue already uses.

See docs/merkezi-yapi-plani.md §2.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import User
from ...deps import owner_db, require_role
from ....schemas.assertions import AssertionCreate, AssertionDecision
from ....services import assertions


router = APIRouter(tags=["assertions"])


# --------------------------------------------------------------- personel


@router.get("/tenant/assertions")
def list_own_assertions(
    entity_id: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(proposed|accepted|rejected|superseded)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "librarian")),
):
    """The caller's library's own claims.

    Scoped by *source*, not by tenant: an assertion has no tenant column, because
    it is a claim about a shared record rather than a row in a library's own
    data. Which claims are yours is decided by which source you act as.
    """

    source_id = assertions.account_source(db, user)

    if source_id is None:
        return {"count": 0, "assertions": []}

    rows = assertions.list_assertions(
        db,
        entity_id=entity_id,
        status=status,
        source_id=source_id,
        limit=limit,
    )

    return {
        "source_system_id": str(source_id),
        "count": len(rows),
        "assertions": [_view(row) for row in rows],
    }


@router.post(
    "/field-assertions",
    status_code=http_status.HTTP_201_CREATED,
)
@router.post(
    "/tenant/assertions",
    status_code=http_status.HTTP_201_CREATED,
)
def file_assertion(
    payload: AssertionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "librarian")),
):
    """File a claim as your own library.

    The source is derived from the account, never from the request. A client that
    could name its own source could file a claim in the ISBN agency's name, and
    the whole trust ranking would be worth nothing.

    `get_db`, not `tenant_db`, and the distinction is architectural rather than
    incidental. An assertion is a claim about a *shared* record, so it lives in
    the global plane -- and the tenant role is deliberately forbidden from writing
    the global plane. Routing this through `tenant_db` fails with "permission
    denied for table field_assertions", which is the isolation working, not a
    missing grant. The session is therefore the application role, and what stops
    it claiming to be somebody else is the trigger, not the role.
    """

    source_id = assertions.account_source(db, user)

    if source_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This account has no source system to assert as",
        )

    # The trigger reads this; without it the insert is refused, which is the
    # point -- the database will not take our word for who we are.
    assertions.bind_source(db, source_id)

    assertion_id = assertions.record(
        db,
        entity_id=payload.entity_id,
        entity_type=payload.entity_type,
        field=payload.field,
        value=payload.value,
        source_id=source_id,
        asserted_by=user.id,
        confidence=payload.confidence,
    )

    # `get_db` closes the session; it does not commit. Without this the claim is
    # written and then rolled back, and the endpoint answers 201 with an id that
    # refers to nothing -- which is exactly what it did on its first run.
    db.commit()

    return {
        "id": str(assertion_id),
        "status": "proposed",
        "source_system_id": str(source_id),
    }


@router.get("/field-assertions/{entity_id}")
def list_entity_assertions(
    entity_id: UUID,
    status: str | None = Query(default=None, pattern="^(proposed|accepted|rejected|superseded)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = assertions.list_assertions(
        db,
        entity_id=entity_id,
        status=status,
        limit=limit,
    )

    return {"count": len(rows), "assertions": [_view(row) for row in rows]}


# --------------------------------------------------------------- küratör


@router.get("/admin/assertions")
def review_queue(
    status: str = Query(default="proposed", pattern="^(proposed|accepted|rejected|superseded)$"),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """The queue, most trusted source first.

    Ordering by `trust_level` before time is the whole reason the column exists:
    when two sources disagree, the ISBN agency's record of an ISBN outranks a
    retailer's, and a reviewer should not have to scroll to find that out.
    """

    rows = assertions.list_assertions(
        db,
        entity_id=entity_id,
        status=status,
        limit=limit,
    )

    return {"count": len(rows), "assertions": [_view(row) for row in rows]}


def _decide(
    assertion_id: str,
    decision: str,
    payload: AssertionDecision,
    db: Session,
    user: User,
) -> dict:
    # The owner credential already satisfies the trigger's curator branch. The
    # binding is set anyway so that the rule is exercised rather than bypassed,
    # and so this keeps working if the decision path ever moves to the app role.
    assertions.bind_curator(db)

    row = db.execute(
        text(
            "select id, status from public.field_assertions where id = :id"
        ),
        {"id": assertion_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Assertion not found",
        )

    if row["status"] != "proposed":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"This assertion has already been {row['status']}",
        )

    if decision == "accepted":
        # Accepting writes the value onto the shared record, so the answer says
        # what actually happened to the catalogue -- not merely that a row changed
        # status. A claim about a column nobody opened returns a reason and
        # changes nothing, which is a different outcome from a refusal.
        result = assertions.accept_and_apply(
            db,
            assertion_id,
            reviewed_by=user.id,
            note=payload.note,
        )

        db.commit()

        applied = sorted((result.applied or {}).keys()) if result else []

        return {
            "id": assertion_id,
            "status": "accepted",
            "applied": applied,
            "dropped": list(result.dropped) if result else [],
            "note": None if applied else (result.reason if result else None),
        }

    assertions.decide(
        db,
        assertion_id,
        status="rejected",
        reviewed_by=user.id,
        note=payload.note,
    )

    db.commit()

    return {"id": assertion_id, "status": "rejected", "applied": []}


@router.post("/admin/assertions/{assertion_id}/accept")
def accept_assertion(
    assertion_id: str,
    payload: AssertionDecision | None = None,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    return _decide(
        assertion_id,
        "accepted",
        payload or AssertionDecision(),
        db,
        user,
    )


@router.post("/admin/assertions/{assertion_id}/reject")
def reject_assertion(
    assertion_id: str,
    payload: AssertionDecision | None = None,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    return _decide(
        assertion_id,
        "rejected",
        payload or AssertionDecision(),
        db,
        user,
    )


@router.post("/assertions/{assertion_id}/decide")
def decide_assertion(
    assertion_id: str,
    payload: AssertionDecision,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    if payload.decision is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision must be 'accepted' or 'rejected'",
        )

    return _decide(assertion_id, payload.decision, payload, db, user)


def _view(row) -> dict:
    value = row["value"]

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass

    return {
        "id": str(row["id"]),
        "entity_id": str(row["entity_id"]),
        "entity_type": row["entity_type"],
        "field": row["field"],
        "value": value,
        "status": row["status"],
        "confidence": row["confidence"],
        "asserted_at": row["asserted_at"],
        "reviewed_at": row["reviewed_at"],
        "review_note": row["review_note"],
        "source": {
            "code": row["source_code"],
            "name": row["source_name"],
            "system_type": row["source_type"],
            "trust_level": row["trust_level"],
        },
    }
