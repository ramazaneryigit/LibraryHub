"""The authority queue: reading it, and deciding from it.

A resemblance is recorded rather than acted on, and this is where a person acts.
The three decisions are deliberately different in weight:

  * **merge** -- these are one person. Repoints the incoming record's relations to
    the existing one, so the works follow, and closes every open suggestion
    between the two.
  * **kept_separate** -- these are two people. Nothing changes except the row, and
    that is the point: the decision is remembered so the same pair is not
    suggested again.
  * **dismissed** -- not worth deciding, usually because the resemblance was a
    shared generic word. Also remembered.

Administrator-only, because merging two authors in a shared catalogue is not a
library's decision about its own data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....db.models import User
from ...deps import owner_db, require_role
from ....services import authority_queue


router = APIRouter(prefix="/admin/authority", tags=["authority"])


class Decision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.get("")
def queue(
    status: str = Query(default="open", pattern="^(open|merged|kept_separate|dismissed)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """Suggestions waiting for a person, best first.

    Ordered by score because the first rows are the ones worth looking at, and the
    generic words that used to dominate the top have been removed from the
    comparison -- so the order now means what it looks like it means.
    """

    rows = authority_queue.list_queue(db, status=status, limit=limit)

    return {
        "count": len(rows),
        "candidates": [
            {
                "id": str(row["id"]),
                "entity_type": row["entity_type"],
                "incoming_name": row["incoming_name"],
                "incoming_entity_id": (
                    str(row["incoming_entity_id"])
                    if row["incoming_entity_id"]
                    else None
                ),
                "candidate_entity_id": str(row["candidate_entity_id"]),
                "candidate_name": row["candidate_name"],
                "score": row["score"],
                "reason": row["reason"],
                "status": row["status"],
                "source": row["source_name"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
    }


def _open(db: Session, candidate_id: str):
    row = db.execute(
        text(
            "select id, incoming_entity_id, candidate_entity_id, status "
            "from public.authority_candidates where id = :id"
        ),
        {"id": candidate_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Authority candidate not found",
        )

    if row["status"] != "open":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"This suggestion was already {row['status']}",
        )

    return row


@router.post("/{candidate_id}/merge")
def merge(
    candidate_id: str,
    payload: Decision | None = None,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """These are one person. Move the works, record it, close the pair.

    The relations are repointed rather than recreated, so the works follow the
    decision. The incoming entity is left in place and unreferenced rather than
    deleted: `entity_merges` exists to record where it went, and a deleted row
    cannot be looked up by whoever wonders next month why an author vanished.
    """

    row = _open(db, candidate_id)
    incoming = row["incoming_entity_id"]
    target = row["candidate_entity_id"]

    moved = 0

    if incoming and str(incoming) != str(target):
        result = db.execute(
            text(
                "update public.work_agent_relation "
                "set agent_entity_id = :target "
                "where agent_entity_id = :incoming "
                "  and not exists ("
                "    select 1 from public.work_agent_relation existing "
                "     where existing.work_entity_id = work_entity_id "
                "       and existing.agent_entity_id = :target)"
            ),
            {"incoming": incoming, "target": target},
        )

        moved = result.rowcount or 0

        # Whatever is left pointed at the incoming entity after the move is a
        # relation the target already had, so it is a duplicate rather than a loss.
        db.execute(
            text(
                "delete from public.work_agent_relation where agent_entity_id = :incoming"
            ),
            {"incoming": incoming},
        )

        # Every open suggestion between the two is now answered by this one.
        db.execute(
            text(
                "update public.authority_candidates "
                "set status = 'merged', reviewed_by = :by, reviewed_at = now(), "
                "    review_note = :note "
                "where status = 'open' and ("
                "  (incoming_entity_id = :incoming and candidate_entity_id = :target) "
                "  or (incoming_entity_id = :target and candidate_entity_id = :incoming))"
            ),
            {"incoming": incoming, "target": target, "by": user.id, "note": payload.note if payload else None},
        )
    else:
        authority_queue.decide(
            db,
            candidate_id,
            status="merged",
            reviewed_by=user.id,
            note=payload.note if payload else None,
        )

    db.commit()

    return {"id": candidate_id, "status": "merged", "relations_moved": moved}


@router.post("/{candidate_id}/separate")
def separate(
    candidate_id: str,
    payload: Decision | None = None,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """These are two people. The decision is the whole point: it is remembered so
    the same pair is not suggested again."""

    _open(db, candidate_id)

    authority_queue.decide(
        db,
        candidate_id,
        status="kept_separate",
        reviewed_by=user.id,
        note=payload.note if payload else None,
    )

    db.commit()

    return {"id": candidate_id, "status": "kept_separate"}


@router.post("/{candidate_id}/dismiss")
def dismiss(
    candidate_id: str,
    payload: Decision | None = None,
    db: Session = Depends(owner_db),
    user: User = Depends(require_role("admin")),
):
    """Not worth deciding -- usually a shared generic word."""

    _open(db, candidate_id)

    authority_queue.decide(
        db,
        candidate_id,
        status="dismissed",
        reviewed_by=user.id,
        note=payload.note if payload else None,
    )

    db.commit()

    return {"id": candidate_id, "status": "dismissed"}
