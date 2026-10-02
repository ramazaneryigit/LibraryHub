"""Reading and applying tenant change proposals.

The two halves of one conversation. A tenant cannot write the global plane --
PostgreSQL refuses it, and that is deliberate -- so an institution that finds a
wrong publication date on a shared record says so with a proposal, and this is
where somebody reads it and decides.

Why accepting and applying are separate
---------------------------------------
Recording a decision writes nothing. Applying is what writes, and it only writes
fields on a whitelist. Collapsing the two would mean a reviewer who believes a
correction is right *in principle* also silently approves whatever shape the JSON
happens to be, and "the database accepted this value" is not the same claim as
"this is a valid publication date".

The whitelist is deliberately short. A tenant may propose a change to shared
bibliographic description; they may not propose their way into the identity
registry, into `entity_merges`, or into anything that would let a correction
become a merge.

Why raw SQL, and why one module serves two callers
--------------------------------------------------
`scripts/review_proposal.py` runs with the owner credential and hands in a
`Connection`; the admin API hands in a `Session` over the same engine. Both
support `execute(text(...))`, so the SQL is written once and the two cannot drift
apart -- which they did: the script carried a copy of this logic and went on
importing a module that had been renamed.

Why every id parameter declares its type
----------------------------------------
A bare `text()` carries no type information, so the driver decides what to do
with a `uuid.UUID`: psycopg3 adapts it, sqlite3 refuses it outright with
"type 'UUID' is not supported". Handing over a string instead does not fix it
either -- PostgreSQL wants the dashed form against a `uuid` column and SQLite
stores `CHAR(32)`, undashed, so one of the two silently matches nothing.
Declaring `type_=Uuid` lets SQLAlchemy apply the right conversion for whichever
engine is answering, which is not a difference the caller should have to know
about.

See docs/architecture-v2.md §0.16 and §0.21.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.types import Uuid

from ..core.text import normalize_text

__all__ = [
    "APPLICABLE_FIELDS",
    "ApplyResult",
    "as_changes",
    "apply_proposal",
    "list_proposals",
    "load_proposal",
    "record_decision",
    "STATUSES",
    "DECISIONS",
]


# Which fields a proposal is allowed to actually move, per entity kind. The table
# and column names come from here and never from the proposal, so a crafted
# `field` cannot reach a column this list does not name.
#
# The table names are unqualified on purpose. Both roles this runs as have
# `public` on their search path, so `works` is `public.works` -- and writing
# `public.works` made the whole apply path unreachable from the SQLite suite,
# where the schema does not exist. The plane is already established by which
# session runs the statement; repeating it in the name bought nothing and cost
# the tests.
#
# `timestamp` is stated per table rather than assumed: none of these three has an
# `updated_at`, and the first version of this wrote `updated_at = now()` for all
# of them and failed on every apply.
APPLICABLE_FIELDS = {
    "work": {
        "table": "works",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "canonical_title",
            "original_title",
            "original_language",
            "description",
        ),
    },
    "expression": {
        "table": "expressions",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "language",
            "expression_form",
            "description",
        ),
    },
    "manifestation": {
        "table": "manifestations",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "publication_statement",
            "publication_date",
            "edition_statement",
            "carrier_type",
            "extent",
            "notes",
        ),
    },
}


# What a reviewer may record. `applied` is reached by applying, not by deciding.
DECISIONS = ("accepted", "rejected")

STATUSES = ("pending", "accepted", "rejected", "withdrawn", "applied")


PROPOSAL_COLUMNS = (
    "id, tenant_id, submitted_by_email, change_type, target_entity_type, "
    "target_entity_id, field_changes, rationale, evidence, status, reviewed_by, "
    "reviewed_at, review_note, applied_at, applied_fields, created_at"
)


PROPOSAL_SELECT = (
    f"select {PROPOSAL_COLUMNS}, "
    "(select t.display_name from control.tenants t where t.id = p.tenant_id) "
    "as tenant_name "
    "from tenant.change_proposals p"
)


def _as_uuid(value: Any) -> Any:
    """A `uuid.UUID`, from whatever the caller or the driver had.

    Raw SQL through `text()` has no result processor, so an id read back from a
    row is a UUID on PostgreSQL and the stored `CHAR(32)` on SQLite; a CLI passes
    the string somebody typed. The typed bind parameters below want a UUID, so
    this is where all three are reconciled.
    """

    if value is None or isinstance(value, uuid.UUID):
        return value

    return uuid.UUID(str(value))


def _typed(sql: str, *identifiers: str) -> TextClause:
    """`text()`, with the named parameters declared as UUIDs.

    See the module docstring: without this, the value reaches the driver as an
    untyped UUID and SQLite refuses it, or as a string and one of the two engines
    matches nothing.
    """

    statement = text(sql)

    if identifiers:
        statement = statement.bindparams(
            *(bindparam(name, type_=Uuid) for name in identifiers)
        )

    return statement


LOAD_PROPOSAL = _typed(f"{PROPOSAL_SELECT} where p.id = :id", "id")

ENTITY_TYPE = _typed("select entity_type from entities where id = :id", "id")


@dataclass
class ApplyResult:
    """What applying did, and what it refused.

    Returned rather than raised so that a CLI can print it and an API can turn it
    into a status code, without either of them owning the rules.
    """

    applied: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


def as_changes(value: Any) -> list:
    """`field_changes` arrives as a list, or as text on a driver without a JSON
    loader -- SQLite returns it as text. Both are accepted so callers do not
    depend on which."""

    if value is None:
        return []

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []

    return value


def list_proposals(
    executor,
    status: str | None = "pending",
    tenant_id=None,
    limit: int | None = None,
) -> list[Mapping]:
    query = PROPOSAL_SELECT
    params: dict = {}
    clauses = []

    if status and status != "all":
        clauses.append("p.status = :status")
        params["status"] = status

    typed: list = []

    if tenant_id is not None:
        clauses.append("p.tenant_id = :tenant_id")
        params["tenant_id"] = _as_uuid(tenant_id)
        typed.append("tenant_id")

    if clauses:
        query += " where " + " and ".join(clauses)

    query += " order by p.created_at"

    if limit is not None:
        query += " limit :limit"
        params["limit"] = limit

    return executor.execute(_typed(query, *typed), params).mappings().all()


def load_proposal(executor, proposal_id) -> Mapping | None:
    return executor.execute(
        LOAD_PROPOSAL,
        {"id": _as_uuid(proposal_id)},
    ).mappings().first()


def record_decision(
    executor,
    proposal_id,
    decision: str,
    reviewer: str,
    note: str | None = None,
) -> int:
    """Record a decision. Writes nothing to the global plane.

    Returns the number of rows changed, which is zero when the proposal is not
    pending -- the caller decides whether that is an error.
    """

    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")

    result = executor.execute(
        _typed(
            "update tenant.change_proposals "
            "set status = :status, reviewed_by = :reviewer, "
            "reviewed_at = CURRENT_TIMESTAMP, review_note = :note, "
            "updated_at = CURRENT_TIMESTAMP "
            "where id = :id and status = 'pending'",
            "id",
        ),
        {
            "id": _as_uuid(proposal_id),
            "status": decision,
            "reviewer": reviewer,
            "note": note,
        },
    )

    return result.rowcount


def apply_proposal(executor, proposal: Mapping) -> ApplyResult:
    """Write the whitelisted fields an accepted proposal asked for."""

    target_id = _as_uuid(proposal["target_entity_id"])

    if target_id is None:
        # An addition has nothing to point at yet; there is no row to write.
        return ApplyResult(
            reason=(
                "Bu bir ekleme önerisi; uygulanacak bir kaydı yok. Kaydı bir "
                "yönetici oluşturmalı."
            )
        )

    entity_type = executor.execute(
        ENTITY_TYPE,
        {"id": target_id},
    ).scalar()

    if entity_type is None:
        return ApplyResult(reason=f"{target_id} diye bir entity yok.")

    kind = entity_type.lower()

    # A proposal carries what the tenant *believes* the target is; the registry is
    # what it actually is. A disagreement is worth stopping for.
    claimed = (proposal["target_entity_type"] or "").lower()

    if claimed and claimed != kind:
        return ApplyResult(reason=f"Öneri '{claimed}' diyor, kayıt '{kind}'.")

    result = apply_fields(
        executor,
        target_id,
        entity_type,
        as_changes(proposal["field_changes"]),
    )

    if result.applied is None:
        return result

    executor.execute(
        _typed(
            "update tenant.change_proposals "
            "set status = 'applied', applied_at = CURRENT_TIMESTAMP, "
            "applied_fields = :applied, updated_at = CURRENT_TIMESTAMP "
            "where id = :id",
            "id",
        ),
        {
            "id": _as_uuid(proposal["id"]),
            "applied": json.dumps(sorted(result.applied)),
        },
    )

    return result


def apply_fields(
    executor,
    entity_id,
    entity_type: str | None,
    changes: list,
) -> ApplyResult:
    """Write whitelisted fields onto one record.

    Shared by the proposal review path and the assertion path. `changes` is the
    shape both produce: a list of `{"field": ..., "proposed": ...}`.

    The whitelist is the point. A curator approving a claim is not a licence to
    write any column anybody names -- `APPLICABLE_FIELDS` decides what a decision
    may touch, and a field outside it is dropped and reported rather than
    silently ignored.
    """

    kind = (entity_type or "").lower()
    allowed = APPLICABLE_FIELDS.get(kind)

    if allowed is None:
        return ApplyResult(
            reason=f"'{kind}' tipi için uygulanabilir alan tanımlı değil."
        )

    assignments: dict = {}
    dropped: list = []

    for change in changes:
        name = change.get("field")

        if name in allowed["fields"]:
            assignments[name] = change.get("proposed")
        else:
            dropped.append(name)

    if not assignments:
        return ApplyResult(
            dropped=dropped,
            reason="Beyaz listedeki hiçbir alan önerilmemiş.",
        )

    # `public.works.normalized_title` is maintained by an ORM event listener, and
    # raw SQL does not fire it. Leaving it stale would silently break matching for
    # exactly the record somebody just corrected -- and it is computed from the
    # column being changed, so it cannot be forgotten here.
    if allowed["table"] == "works" and "canonical_title" in assignments:
        assignments["normalized_title"] = normalize_text(
            assignments["canonical_title"] or ""
        )

    rendered = ", ".join(f"{name} = :{name}" for name in assignments)

    # `CURRENT_TIMESTAMP`, not `now()`: the latter is PostgreSQL's and SQLite has
    # no such function, which made this unreachable from the test suite.
    if allowed["timestamp"]:
        rendered += f", {allowed['timestamp']} = CURRENT_TIMESTAMP"

    executor.execute(
        _typed(
            f"update {allowed['table']} set {rendered} "
            f"where {allowed['key']} = :target_id",
            "target_id",
        ),
        {**assignments, "target_id": _as_uuid(entity_id)},
    )

    # The values, not a set of names: `ApplyResult.applied` has always carried
    # what was written, and callers read it.
    return ApplyResult(applied=assignments, dropped=dropped)
