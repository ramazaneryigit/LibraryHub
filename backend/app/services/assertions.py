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
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.types import Uuid

__all__ = [
    "accept_and_apply",
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

    Library staff act as their tenant's source and platform administrators as the
    platform source. Other principal types need an explicit source-system mapping;
    they must not inherit the platform identity merely because they have no tenant.
    """

    principal_kind = getattr(user, "principal_kind", None)
    tenant_id = getattr(user, "tenant_id", None)

    if principal_kind == "tenant_staff" and tenant_id is not None:
        return source_id_for_tenant(executor, tenant_id)

    if principal_kind == "platform" and tenant_id is None:
        return executor.execute(
            text("select id from public.source_systems where code = 'platform'")
        ).scalar()

    return None


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
    encoded_value = json.dumps(value)

    executor.execute(
        text(
            "insert into public.field_assertions "
            "(id, entity_id, field_name, value_text, value_json, source_system_id, "
            " asserted_at, status, confidence) "
            "values (:id, :entity_id, :field, :value, cast(:value as json), "
            "        :source_id, now(), 'proposed', :confidence)"
        ),
        {
            "id": assertion_id,
            "entity_id": entity_id,
            "field": field,
            "value": encoded_value,
            "source_id": source_id,
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

    old_status = executor.execute(
        text("select status from public.field_assertions where id = :id"),
        {"id": assertion_id},
    ).scalar()

    if old_status is None:
        return

    result = executor.execute(
        text(
            "update public.field_assertions "
            "set status = :status, reviewed_by = :reviewed_by, "
            "    reviewed_at = now(), observation_notes = :note "
            "where id = :id and status = 'proposed'"
        ),
        {
            "id": assertion_id,
            "status": status,
            "reviewed_by": reviewed_by,
            "note": note,
        },
    )

    if result.rowcount:
        executor.execute(
            text(
                "insert into public.field_assertion_audits "
                "(id, assertion_id, old_status, new_status, changed_by_user_id, "
                " reason, changed_at) "
                "values (:id, :assertion_id, :old_status, :new_status, "
                "        :changed_by, :reason, now())"
            ),
            {
                "id": uuid.uuid4(),
                "assertion_id": assertion_id,
                "old_status": old_status,
                "new_status": status,
                "changed_by": reviewed_by,
                "reason": note,
            },
        )


def accept_and_apply(
    executor,
    assertion_id,
    *,
    reviewed_by,
    note: str | None = None,
):
    """Accept a claim and write its value onto the shared record.

    Accepting is not a status change; it is an edit to the catalogue. So this is
    the point where a claim becomes a fact, and it goes through exactly the write
    path the proposal queue uses -- `proposal_review.apply_fields` -- rather than a
    second one. The whitelist in `APPLICABLE_FIELDS` decides what a claim may
    touch: an assertion about a column nobody agreed to open is refused there,
    with a reason, instead of being written because a curator clicked once.

    A refusal is not an error. A claim can be accepted as a true statement about
    the world while touching nothing -- and the caller is told which happened.
    """

    # Imported here rather than at module load: `proposal_review` reads the same
    # models and the same text helpers, and a cycle would make the import order
    # matter for no benefit.
    from .proposal_review import apply_fields

    row = executor.execute(
        text(
            "select a.id, a.entity_id, e.entity_type, a.field_name as field, "
            "       coalesce(a.value_json::text, a.value_text) as value, a.status "
            "from public.field_assertions a "
            "join public.entities e on e.id = a.entity_id "
            "where a.id = :id"
        ),
        {"id": assertion_id},
    ).mappings().first()

    if row is None:
        return None

    value = row["value"]

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass

    result = apply_fields(
        executor,
        row["entity_id"],
        row["entity_type"],
        [{"field": row["field"], "proposed": value}],
    )

    decide(
        executor,
        assertion_id,
        status="accepted",
        reviewed_by=reviewed_by,
        note=note,
    )

    return result


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
        "select a.id, a.entity_id, e.entity_type, a.field_name as field, "
        "       coalesce(a.value_json::text, a.value_text) as value, a.status, "
        "       a.asserted_at, a.reviewed_at, "
        "       a.observation_notes as review_note, a.confidence, "
        "       s.code as source_code, s.name as source_name, "
        "       s.system_type as source_type, s.trust_level "
        "from public.field_assertions a "
        "join public.entities e on e.id = a.entity_id "
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
