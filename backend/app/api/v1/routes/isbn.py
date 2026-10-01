"""The ISBN agency's workspace.

One participant, one job: say what is coming. So there are two endpoints and no
more -- declare, and read back what has been declared. Everything about *acquiring*
a declared book belongs to a library, and appears in `/kutuphane` the moment that
library creates a holding.

Access is `isbn_agency`. The principal kind was declared in migration
`a4c7e2b91f38` and until now nothing used it; this is the first participant that
does.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....db import get_db
from ....db.models import User
from ...deps import current_user
from ....services import isbn


router = APIRouter(prefix="/isbn", tags=["isbn"])


class Declaration(BaseModel):
    """One publication the agency is assigning an ISBN to."""

    title: str = Field(min_length=1, max_length=1000)
    isbn: str | None = Field(default=None, max_length=40)
    author: str | None = Field(default=None, max_length=500)
    publisher: str | None = Field(default=None, max_length=500)
    publication_date: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=50)
    carrier_type: str | None = Field(default=None, max_length=100)
    edition_statement: str | None = Field(default=None, max_length=500)
    status: str = Field(default="announced", pattern="^(announced|in_press)$")


class DeclarationBatch(BaseModel):
    """A batch, because ISBNs are assigned in batches, not one at a time."""

    declarations: list[Declaration] = Field(min_length=1, max_length=500)


def require_agency(user: User = Depends(current_user)) -> User:
    """Only the agency may declare what the agency knows.

    Not `require_role`: `role` says what somebody may do inside a library, and the
    agency is not inside one. What it may do follows from *which participant it
    is*, which is `principal_kind`.
    """

    if user.principal_kind != "isbn_agency":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="This workspace belongs to the ISBN agency",
        )

    return user


@router.get("/publications")
def declared(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_agency),
):
    """Everything declared and not yet released."""

    rows = isbn.list_declared(db, limit=limit)

    return {
        "count": len(rows),
        "publications": [
            {
                "manifestation_entity_id": str(row["manifestation_entity_id"]),
                "work_entity_id": str(row["work_entity_id"]),
                "title": row["canonical_title"],
                "isbn": row["isbn"],
                "publisher": row["publisher"],
                "publication_date": row["publication_date"],
                "carrier_type": row["carrier_type"],
                "publication_status": row["publication_status"],
            }
            for row in rows
        ],
    }


@router.post(
    "/publications",
    status_code=http_status.HTTP_201_CREATED,
)
def declare(
    payload: DeclarationBatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_agency),
):
    """Declare one or many publications.

    Partial success is reported rather than hidden. A batch of two hundred rows
    from a spreadsheet will contain duplicates and mistakes, and failing the whole
    batch because of row ninety-one means the operator has to find the difference
    between what they sent and what arrived.
    """

    source_id = isbn.agency_source(db)
    created = []
    refused = []

    for index, declaration in enumerate(payload.declarations):
        try:
            result = isbn.declare_publication(
                db,
                title=declaration.title,
                isbn=declaration.isbn,
                author=declaration.author,
                publisher=declaration.publisher,
                publication_date=declaration.publication_date,
                language=declaration.language,
                carrier_type=declaration.carrier_type,
                edition_statement=declaration.edition_statement,
                status=declaration.status,
            )
        except Exception as error:  # noqa: BLE001 - the reason is the report
            db.rollback()

            refused.append({"index": index, "title": declaration.title, "reason": str(error)[:200]})
            continue

        created.append(
            {
                "index": index,
                "manifestation_entity_id": str(result["manifestation_entity_id"]),
                "title": result["title"],
                "isbn": result["isbn"],
                "publication_status": result["publication_status"],
            }
        )

    if created:
        db.commit()

    return {
        "source_system_id": str(source_id) if source_id else None,
        "created": len(created),
        "refused": len(refused),
        "declarations": created,
        "problems": refused,
    }
