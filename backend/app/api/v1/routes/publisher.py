"""The publisher's workspace.

Three questions: how many of my titles are out there, which libraries hold them,
and what is coming that a library could order. Access follows `principal_kind` --
a publisher is not inside a library, so `role` has nothing to say about it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import User
from ...deps import current_user
from ....services import isbn, publisher


router = APIRouter(prefix="/publisher", tags=["publisher"])


class TitleDeclaration(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    isbn: str | None = Field(default=None, max_length=40)
    author: str | None = Field(default=None, max_length=500)
    publication_date: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=50)
    carrier_type: str | None = Field(default=None, max_length=100)
    edition_statement: str | None = Field(default=None, max_length=500)


def require_publisher(user: User = Depends(current_user)) -> User:
    if user.principal_kind != "publisher":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="This workspace belongs to a publisher",
        )

    return user


def _bound(user: User) -> None:
    if user.subject_entity_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                "This account is not bound to a publisher record, so 'my titles' "
                "cannot be answered"
            ),
        )


@router.get("/summary")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_publisher),
):
    _bound(user)

    return dict(publisher.summary(db, user))


@router.get("/titles")
def titles(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_publisher),
):
    """Titles, most widely held first -- the number the publisher came for."""

    _bound(user)

    rows = publisher.publisher_titles(db, user, limit=limit)

    return {
        "count": len(rows),
        "titles": [
            {
                "work_entity_id": str(row["work_entity_id"]),
                "title": row["title"],
                "manifestations": row["manifestations"],
                "holdings": row["holdings"],
                "libraries": row["libraries"],
            }
            for row in rows
        ],
    }


@router.get("/titles/{work_id}/libraries")
def holders(
    work_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_publisher),
):
    """Which libraries hold one title, and which printing of it.

    Holdings, not copies: a library that has catalogued a title but not yet
    barcoded a copy still holds it, and counting copies would hide exactly the
    libraries in the middle of processing.
    """

    _bound(user)

    rows = publisher.library_report(db, user, work_id)

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


@router.post("/titles", status_code=http_status.HTTP_201_CREATED)
def declare(
    payload: TitleDeclaration,
    db: Session = Depends(get_db),
    user: User = Depends(require_publisher),
):
    """Announce a title.

    `announced`, never `published`: a publisher typing a record in has not
    necessarily printed it yet, and a catalogue that assumes otherwise would tell
    readers a book is on a shelf before it exists. When a library acquires it, the
    holding they create makes it real -- and that is the only thing that should.
    """

    _bound(user)

    publisher_name = db.execute(
        text(
            "select canonical_name from public.collective_agents where entity_id = :id"
        ),
        {"id": user.subject_entity_id},
    ).scalar()

    result = isbn.declare_publication(
        db,
        title=payload.title,
        isbn=payload.isbn,
        author=payload.author,
        publisher=publisher_name,
        publication_date=payload.publication_date,
        language=payload.language,
        carrier_type=payload.carrier_type,
        edition_statement=payload.edition_statement,
        status="announced",
    )

    db.commit()

    return {
        "work_entity_id": str(result["work_entity_id"]),
        "manifestation_entity_id": str(result["manifestation_entity_id"]),
        "title": result["title"],
        "publication_status": result["publication_status"],
    }
