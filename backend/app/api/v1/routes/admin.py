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
from ....db import get_db
from ....db.models import User
from ....schemas.admin import PasswordReset, ProposalDecision, UserCreate, UserUpdate
from ....services.proposal_review import (
    STATUSES,
    apply_proposal,
    as_changes,
    list_proposals,
    load_proposal,
    record_decision,
)
from ....services.staff_directory import (
    AccountRefused,
    ROLES,
    create_user,
    get_tenant,
    get_user,
    list_tenants,
    list_users,
    revoke_sessions,
    set_password,
    update_user,
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


# --------------------------------------------------------------------- views


def _tenant_view(row) -> dict:
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "display_name": row["display_name"],
        "staff_count": row["staff_count"],
        "created_at": _stamp(row["created_at"]),
    }


def _user_view(row) -> dict:
    return {
        "id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]) if row["tenant_id"] else None,
        "tenant_name": row["tenant_name"],
        "tenant_slug": row["tenant_slug"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "account_kind": row["account_kind"],
        "email_verified_at": _stamp(row["email_verified_at"]),
        "is_active": row["is_active"],
        "created_at": _stamp(row["created_at"]),
        "updated_at": _stamp(row["updated_at"]),
    }


# -------------------------------------------------------------- institutions
#
# These read `control.tenants` through the ordinary application session, not the
# owner credential. The application role has `SELECT` on that table and nothing
# else, so institutions are read here and created by `register_domain.py`.


@router.get("/tenants")
def tenants(db: Session = Depends(get_db)):
    rows = list_tenants(db)

    return {
        "count": len(rows),
        "tenants": [_tenant_view(row) for row in rows],
    }


@router.get("/tenants/{tenant_id}")
def tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    row = get_tenant(db, tenant_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kurum bulunamadı.",
        )

    return _tenant_view(row)


# ------------------------------------------------------------------ accounts
#
# Through `get_db`, deliberately, and this is the one place where that choice is
# load-bearing. `owner_db` is a superuser, so writing accounts through it would
# bypass `guard_application_account_writes` -- the trigger that stops an
# application role from promoting anybody to administrator or from rewriting an
# administrator's password. The ordinary session is what keeps that true.


@router.get("/users")
def users(
    tenant_id: uuid.UUID | None = None,
    role: str | None = Query(default=None, description="admin, librarian, viewer"),
    include_platform: bool = Query(
        default=True,
        description="Kiracısız platform hesaplarını da listele.",
    ),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if role is not None and role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bilinmeyen rol: '{role}'. Geçerli: {', '.join(ROLES)}",
        )

    rows = list_users(
        db,
        tenant_id=tenant_id,
        role=role,
        include_platform=include_platform,
        limit=limit,
    )

    return {
        "count": len(rows),
        "accounts": [_user_view(row) for row in rows],
    }


@router.get("/users/{user_id}")
def account(user_id: uuid.UUID, db: Session = Depends(get_db)):
    row = get_user(db, user_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hesap bulunamadı.",
        )

    return _user_view(row)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def open_account(payload: UserCreate, db: Session = Depends(get_db)):
    """Open a staff account.

    The account is **unverified**, and that is the guard trigger's doing rather
    than an omission: an application role may not create an account that is
    already verified, so the holder has to confirm the address. The owner-running
    script may do both; this path deliberately has less authority.
    """

    try:
        row = create_user(
            db,
            tenant_id=payload.tenant_id,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role,
            password=payload.password,
        )

        db.commit()

    except AccountRefused as refusal:
        db.rollback()

        raise HTTPException(
            status_code=refusal.status_code,
            detail=str(refusal),
        )

    return _user_view(row)


@router.patch("/users/{user_id}")
def change_account(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
):
    """Change an ordinary account. Administrator accounts are refused.

    Deactivating also ends every live session: an account switched off while its
    session keeps working has not been switched off.
    """

    try:
        row = update_user(
            db,
            user_id,
            display_name=payload.display_name,
            role=payload.role,
            is_active=payload.is_active,
        )

        db.commit()

    except AccountRefused as refusal:
        db.rollback()

        raise HTTPException(
            status_code=refusal.status_code,
            detail=str(refusal),
        )

    return _user_view(row)


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: uuid.UUID,
    payload: PasswordReset,
    db: Session = Depends(get_db),
):
    """Set a new password, and end the sessions the old one opened."""

    try:
        result = set_password(db, user_id, payload.password)

        db.commit()

    except AccountRefused as refusal:
        db.rollback()

        raise HTTPException(
            status_code=refusal.status_code,
            detail=str(refusal),
        )

    return {
        "user": _user_view(result["user"]),
        "revoked_sessions": result["revoked_sessions"],
    }


@router.post("/users/{user_id}/sessions/revoke")
def revoke(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """End every live session for an account, without changing anything else."""

    row = get_user(db, user_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hesap bulunamadı.",
        )

    revoked = revoke_sessions(db, user_id)

    db.commit()

    return {"user_id": str(user_id), "revoked_sessions": revoked}
