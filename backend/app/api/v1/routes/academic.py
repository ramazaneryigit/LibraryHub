"""The academician's profile.

An academician is not inside a library, so access follows `principal_kind` rather
than `role` -- the same distinction the publisher workspace draws, for the same
reason.

The account is bound to a `persons` entity through an ORCID iD. What that proves
and what it does not is written down in `services/academic`: the check digit
catches a mistyped iD, and only OAuth would prove the iD belongs to whoever signed
in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import User
from ...deps import current_user
from ....services import academic


router = APIRouter(prefix="/academician", tags=["academician"])


class OrcidClaim(BaseModel):
    orcid: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=500)


def require_academician(user: User = Depends(current_user)) -> User:
    if user.principal_kind != "academician":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="This workspace belongs to an academician account",
        )

    return user


@router.get("/profile")
def profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_academician),
):
    """Who this account speaks for.

    `bound: false` is a normal answer, not an error: an academician registers
    before their ORCID is known, and the screen's job is then to ask for it.
    """

    return academic.profile(db, user)


@router.post("/orcid")
def bind(
    payload: OrcidClaim,
    db: Session = Depends(get_db),
    user: User = Depends(require_academician),
):
    """Bind this account to the person its ORCID belongs to.

    A refused iD is a 422 with the reason, not a 500: `normalize_orcid` returns
    None for anything whose check digit does not add up, and that is a fact about
    the request rather than a failure of the system.
    """

    try:
        result = academic.bind_orcid(
            db,
            user,
            payload.orcid,
            payload.display_name,
        )
    except ValueError as error:
        db.rollback()

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    db.commit()

    return {
        "orcid": result["orcid"],
        "person_entity_id": str(result["person_entity_id"]),
        "created": result["created"],
    }


@router.get("/works")
def works(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_academician),
):
    """This person's works, most widely held first.

    Authorship through a work *and* through an expression inside one: a profile
    that showed only the first would hide every translated or illustrated title.
    """

    rows = academic.profile_works(db, user, limit=limit)

    return {
        "count": len(rows),
        "works": [
            {
                "work_entity_id": str(row["work_entity_id"]),
                "title": row["title"],
                "holdings": row["holdings"],
                "libraries": row["libraries"],
            }
            for row in rows
        ],
    }


@router.get("/works/{work_id}/libraries")
def holders(
    work_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_academician),
):
    """Which libraries hold one of this person's works.

    Deliberately not scoped to the author. Which libraries hold a published book
    is public information -- it is what the union catalogue is for -- and hiding
    it from the author while showing it to the publisher would be hard to justify.
    """

    rows = academic.libraries_holding(db, work_id)

    return {
        "count": len(rows),
        "libraries": [
            {
                "library": row["library"],
                "institution": row["institution"],
                "edition": row["edition"],
                "holdings": row["holdings"],
            }
            for row in rows
        ],
    }
