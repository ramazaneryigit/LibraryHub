"""Curation of the shared record.

Everything under `/admin` is behind `require_admin` and runs on the owner
credential, for one reason: change proposals live in `tenant.change_proposals`,
which is protected by row level security keyed on `libraryhub.tenant_id`. A
reviewer has to see what every institution has raised at once, and has no tenant
to bind -- so under the application role the policies would, correctly, show
nothing at all.

That makes these the most privileged routes in the application, and the
dependency chain starts at `require_admin` rather than ending there.

Reading a proposal is one act; accepting it is another; applying it is a third.
They are separate endpoints because they are separate decisions -- see
`app/services/proposal_review.py` for why, and `docs/architecture-v2.md` §0.16.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...deps import current_user, owner_db, require_admin
from ....db.models import User
from ....schemas.admin import ProposalDecision
from ....services.proposal_review import (
    STATUSES,
    apply_proposal,
    as_changes,
    list_proposals,
    load_proposal,
    record_decision,
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _stamp(value):
    """A timestamp as ISO text.

    PostgreSQL hands back a `datetime`; SQLite hands back the stored string,
    because it has no native timestamp type. Both are accepted for the same
    reason `as_changes` accepts both a list and JSON text: the response shape
    should not depend on which engine answered.
    """

    if value is None or isinstance(value, str):
        return value

    return value.isoformat()


def _proposal_view(proposal) -> dict:
    """One proposal as JSON.

    `field_changes` and `applied_fields` are JSON columns: PostgreSQL hands back
    the parsed value, SQLite hands back text. `as_changes` accepts both, so the
    response shape does not depend on which engine answered.
    """

    return {
        "id": str(proposal["id"]),
        "tenant_id": str(proposal["tenant_id"]),
        "tenant_name": proposal["tenant_name"],
        "submitted_by_email": proposal["submitted_by_email"],
        "change_type": proposal["change_type"],
        "target_entity_type": proposal["target_entity_type"],
        "target_entity_id": (
            str(proposal["target_entity_id"])
            if proposal["target_entity_id"]
            else None
        ),
        "field_changes": as_changes(proposal["field_changes"]),
        "rationale": proposal["rationale"],
        "evidence": proposal["evidence"],
        "status": proposal["status"],
        "reviewed_by": proposal["reviewed_by"],
        "reviewed_at": _stamp(proposal["reviewed_at"]),
        "review_note": proposal["review_note"],
        "applied_at": _stamp(proposal["applied_at"]),
        "applied_fields": as_changes(proposal["applied_fields"]),
        "created_at": _stamp(proposal["created_at"]),
    }


@router.get("/proposals")
def proposals(
    status_filter: str = Query(
        default="pending",
        alias="status",
        description="Bir durum, ya da hepsi için 'all'.",
    ),
    tenant_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(owner_db),
):
    """What is waiting to be read, oldest first."""

    if status_filter != "all" and status_filter not in STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Bilinmeyen durum: '{status_filter}'. "
                f"Geçerli: {', '.join(STATUSES)}, all"
            ),
        )

    rows = list_proposals(
        db,
        status=status_filter,
        tenant_id=tenant_id,
        limit=limit,
    )

    return {
        "count": len(rows),
        "status": status_filter,
        "proposals": [_proposal_view(row) for row in rows],
    }


@router.get("/proposals/summary")
def proposals_summary(db: Session = Depends(owner_db)):
    """Counts by status, for a panel that has to show where the work is.

    Declared before `/proposals/{proposal_id}` on purpose: routes match in the
    order they are added, and the parameterised one would otherwise swallow
    `summary` and fail parsing it as a UUID.
    """

    rows = list_proposals(db, status="all")

    counts: dict = {name: 0 for name in STATUSES}

    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return {
        "total": len(rows),
        "counts": counts,
        "waiting": counts.get("pending", 0),
    }


@router.get("/proposals/{proposal_id}")
def proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(owner_db),
):
    row = load_proposal(db, proposal_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Öneri bulunamadı.",
        )

    return _proposal_view(row)


@router.post("/proposals/{proposal_id}/decision")
def decide(
    proposal_id: uuid.UUID,
    payload: ProposalDecision,
    user: User = Depends(current_user),
    db: Session = Depends(owner_db),
):
    """Record the decision. Writes nothing to the shared record.

    `reviewed_by` is taken from the session. Until this endpoint existed the
    reviewer was a name typed on a command line, which recorded a claim rather
    than an identity.
    """

    row = load_proposal(db, proposal_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Öneri bulunamadı.",
        )

    if row["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu öneri zaten '{row['status']}' durumunda; "
                "yalnızca bekleyen bir öneri karara bağlanabilir."
            ),
        )

    changed = record_decision(
        db,
        proposal_id,
        payload.decision,
        user.email,
        payload.note,
    )

    if not changed:
        # The status check above read a row that a concurrent request has since
        # moved; the UPDATE carried the same guard, so nothing was written.
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Öneri bu sırada değişti; yeniden okuyun.",
        )

    db.commit()

    return _proposal_view(load_proposal(db, proposal_id))


@router.post("/proposals/{proposal_id}/apply")
def apply(
    proposal_id: uuid.UUID,
    db: Session = Depends(owner_db),
):
    """Write the accepted changes, and report what was refused.

    Only an accepted proposal can be applied -- an administrator who rejects a
    correction should not be able to apply it by asking a different endpoint, and
    a pending one has not been read yet.
    """

    row = load_proposal(db, proposal_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Öneri bulunamadı.",
        )

    if row["status"] != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Yalnızca kabul edilmiş bir öneri uygulanabilir; "
                f"bu öneri '{row['status']}'."
            ),
        )

    result = apply_proposal(db, row)

    if not result.ok:
        # Nothing was written: every refusal in `apply_proposal` happens before
        # the first UPDATE. Rolling back says so rather than leaving it implied.
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.reason,
        )

    db.commit()

    return {
        "applied": result.applied,
        "dropped": result.dropped,
        "proposal": _proposal_view(load_proposal(db, proposal_id)),
    }
