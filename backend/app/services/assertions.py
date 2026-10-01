"""Reading and writing field assertions.

The database enforces two things and this module exists to satisfy them rather
than to duplicate them: an assertion may only be filed as the source the session
is acting as, and only a curator may decide one. Both are checked by the trigger
in migration `a4c7e2b91f38`, so the job here is to bind the session correctly and
then get out of the way.

A participant does not get to choose its own source. It is derived from the
account -- a library's staff act as that library's source system -- because
anything the client could supply here is a claim about identity, and a claim
about identity is the one thing that must not come from the client.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.sql import TextClause
from sqlalchemy.types import Uuid

__all__ = [
    "account_source",
    "bind_curator",
    "bind_source",
    "decide",
    "list_assertions",
    "record",
    "source_id_for_tenant",
]


def source_id_for_tenant(executor, tenant_id) -> Any:
    """The source system a library asserts as.

    Seeded by the migration as `tenant:<slug>`; looked up by joining through the
    tenant rather than by rebuilding the slug, so a renamed tenant does not
    silently stop having a source.
    """

    return executor.execute(
        text(
            "select s.id from public.source_systems s "
            "join control.tenants t on s.code = 'tenant:' || t.slug "
            "where t.id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    ).scalar()


def account_source(executor, user) -> Any:
    """The source this account acts as.

    A platform account is the platform source; a library's staff are that
    library's. The four participants who are not libraries yet have no source of
    their own -- when they get workspaces, this is the function that learns where
    to find them.
    """

    if getattr(user, "tenant_id", None) is not None:
        return source_id_for_tenant(executor, user.tenant_id)

    return executor.execute(
        text("select id from public.source_systems where code = 'platform'")
    ).scalar()


def _bind(executor, name: str, value: str) -> None:
    # `is_local => true`, so the setting dies with the transaction: a pooled
    # connection must never carry one request's identity into the next.
    executor.execute(
        text("select set_config(:name, :value, true)"),
        {"name": name, "value": value},
    )


def bind_source(executor, source_id) -> None:
    """Act as this source for the rest of the transaction."""

    _bind(executor, "libraryhub.source_system_id", str(source_id))


def bind_curator(executor) -> None:
    """Act as a curator: may decide, may not rewrite."""

    _bind(executor, "libraryhub.assertion_curator", "on")


def record(
    executor,
    *,
    entity_id,
    entity_type: str,
    field: str,
    value: Any,
    source_id,
    asserted_by=None,
    confidence: float | None = None,
) -> uuid.UUID:
    """File a claim. Returns its id.

    The value is stored as JSON, so a caller passes the shape the field actually
    takes -- a string, a list of contributors, a date -- rather than a rendering
    of it.
    """

    import json

    assertion_id = uuid.uuid4()

    executor.execute(
        text(
            "insert into public.field_assertions "
            "(id, entity_id, entity_type, field, value, source_system_id, "
            " asserted_by, asserted_at, status, confidence) "
            "values (:id, :entity_id, :entity_type, :field, cast(:value as jsonb), "
            "        :source_id, :asserted_by, now(), 'proposed', :confidence)"
        ),
        {
            "id": assertion_id,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "field": field,
            "value": json.dumps(value),
            "source_id": source_id,
            "asserted_by": asserted_by,
            "confidence": confidence,
        },
    )

    return assertion_id


def decide(
    executor,
    assertion_id,
    *,
    status: str,
    reviewed_by,
    note: str | None = None,
) -> None:
    """Accept or reject. Requires the curator binding."""

    if status not in ("accepted", "rejected"):
        raise ValueError("a decision is 'accepted' or 'rejected'")

    executor.execute(
        text(
            "update public.field_assertions "
            "set status = :status, reviewed_by = :reviewed_by, "
            "    reviewed_at = now(), review_note = :note "
            "where id = :id and status = 'proposed'"
        ),
        {
            "id": assertion_id,
            "status": status,
            "reviewed_by": reviewed_by,
            "note": note,
        },
    )


def list_assertions(
    executor,
    *,
    entity_id=None,
    status: str | None = None,
    source_id=None,
    limit: int = 100,
) -> list[Mapping]:
    """Assertions, newest first, with the source that made each claim named.

    The name matters more than the id: a reviewer deciding between two values
    needs to see *who* is claiming, and `trust_level` is what orders them.
    """

    # Every optional filter is cast, and the null check is written with `cast`
    # rather than bare `:name is null`. PostgreSQL cannot infer a type for a
    # parameter that only ever appears in `is null`, and answers "could not
    # determine data type of parameter" -- which reaches the client as a 500.
    statement = (
        "select a.id, a.entity_id, a.entity_type, a.field, a.value, a.status, "
        "       a.asserted_at, a.reviewed_at, a.review_note, a.confidence, "
        "       s.code as source_code, s.name as source_name, "
        "       s.system_type as source_type, s.trust_level "
        "from public.field_assertions a "
        "join public.source_systems s on s.id = a.source_system_id "
        "where (cast(:entity_id as uuid) is null or a.entity_id = cast(:entity_id as uuid)) "
        "  and (cast(:status as text) is null or a.status = cast(:status as text)) "
        "  and (cast(:source_id as uuid) is null "
        "       or a.source_system_id = cast(:source_id as uuid)) "
        "order by s.trust_level desc, a.asserted_at desc "
        "limit :limit"
    )

    parameters = {
        "entity_id": str(entity_id) if entity_id else None,
        "status": status,
        "source_id": str(source_id) if source_id else None,
        "limit": limit,
    }

    return executor.execute(text(statement), parameters).mappings().all()
