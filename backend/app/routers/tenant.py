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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..control_models import User
from ..dependencies import current_user, tenant_db


router = APIRouter(
    prefix="/tenant",
    tags=["tenant"],
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
