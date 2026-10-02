"""Loading a library's MARC file into the catalogue.

The pipeline is three steps and this is the third: `marc.parse_records` reads the
bytes, `marc_mapping.map_record` decides what a record means, and this writes what
it decided. Each is separable, which is why a mapping mistake is found by a unit
test rather than by a half-imported collection.

Why the owner credential
------------------------
A batch belongs to one library but writes rows for many: works and manifestations
in the shared plane, holdings in the tenant plane. A tenant session can only see
one tenant, so loading a file for another library through one would be impossible
by construction. This is an administrative import, it runs as the operator, and
`tenant.holdings` is written with `tenant_id` stated explicitly -- which the owner
must do precisely because no policy is doing it.

The library code
----------------
`852$b` is resolved against `control.branches.code`, normalized the way the
mapping normalizes it. So the "code list" a library has to supply has a home
already: it is the branch codes the platform administrator maintains. Today every
branch in this database carries the code `MAIN`, which resolves nothing -- a
record saying `TR-KKU` finds no library, and the report says so by name rather
than dropping the record.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from sqlalchemy import text

from ..core.ids import uuid7
from ..core.marc import MarcError, parse_records
from ..core.marc_mapping import MappedRecord, map_record, normalize_library_code
from ..core.text import normalize_text
from . import authority_queue

__all__ = ["ingest", "list_batches", "read_batch", "resolve_branch"]


def list_batches(executor, *, limit: int = 50) -> list[Mapping]:
    """Every import run, newest first, without the report bodies.

    The list is for choosing; the report is for reading. Sending two hundred
    problem lists to draw a table would be most of a megabyte to answer a question
    nobody asked yet.
    """

    return executor.execute(
        text(
            "select id, source_system, status, total, created, unchanged, failed, "
            "       started_at, finished_at, created_at "
            "from public.ingestion_batches "
            "order by created_at desc "
            "limit :limit"
        ),
        {"limit": limit},
    ).mappings().all()


def read_batch(executor, batch_id) -> Mapping | None:
    """One run, with the report it produced."""

    row = executor.execute(
        text(
            "select id, source_system, status, total, created, unchanged, failed, "
            "       started_at, finished_at, created_at, report "
            "from public.ingestion_batches where id = :id"
        ),
        {"id": batch_id},
    ).mappings().first()

    if row is None:
        return None

    return row


def resolve_branch(executor, code: str) -> Any:
    """The branch a MARC institution code names, if any."""

    return executor.execute(
        text(
            "select id, tenant_id from control.branches "
            "where upper(replace(coalesce(code, ''), ' ', '-')) = :code "
            "limit 1"
        ),
        {"code": normalize_library_code(code)},
    ).mappings().first()


def _agent_for(executor, name: str, agent_type: str) -> uuid.UUID:
    """Delegates, so a MARC file and an ISBN declaration agree about authorship.

    The body moved to `authority_queue.agent_for` when the ISBN path turned out to
    be writing the author into the work's description instead of creating a person.
    One implementation, two callers.
    """

    return authority_queue.agent_for(executor, name, agent_type)


def _write_record(executor, mapped: MappedRecord) -> Mapping:
    """One mapped record, as rows. Returns the ids it created."""

    work_id = uuid7()
    expression_id = uuid7()
    manifestation_id = uuid7()

    # `entities` before its subtype in every case. The triggers are deferred, but
    # this order has already cost one debugging session (§0.19).
    executor.execute(
        text(
            "insert into public.entities (id, entity_type, created_at, updated_at) "
            "values (:id, 'WORK', now(), now())"
        ),
        {"id": work_id},
    )
    executor.execute(
        text(
            "insert into public.works "
            "(entity_id, canonical_title, original_title, description, created_at) "
            "values (:id, :title, :subtitle, :author, now())"
        ),
        {
            "id": work_id,
            "title": mapped.title,
            "subtitle": mapped.subtitle,
            "author": (
                "; ".join(a.name for a in mapped.authors) if mapped.authors else None
            ),
        },
    )

    executor.execute(
        text(
            "insert into public.entities (id, entity_type, created_at, updated_at) "
            "values (:id, 'EXPRESSION', now(), now())"
        ),
        {"id": expression_id},
    )
    executor.execute(
        text(
            "insert into public.expressions (entity_id, language) "
            "values (:id, :language)"
        ),
        {"id": expression_id, "language": mapped.language},
    )
    executor.execute(
        text(
            "insert into public.work_expression "
            "(work_entity_id, expression_entity_id) values (:work, :expression)"
        ),
        {"work": work_id, "expression": expression_id},
    )

    statement = " ".join(
        part
        for part in (
            mapped.publication_place,
            ":" if mapped.publication_place and mapped.publisher else None,
            mapped.publisher + "," if mapped.publisher else None,
            mapped.publication_date,
        )
        if part
    ) or None

    executor.execute(
        text(
            "insert into public.entities (id, entity_type, created_at, updated_at) "
            "values (:id, 'MANIFESTATION', now(), now())"
        ),
        {"id": manifestation_id},
    )
    executor.execute(
        text(
            "insert into public.manifestations "
            "(entity_id, publication_statement, publication_date, edition_statement, "
            " carrier_type, publication_status) "
            "values (:id, :statement, :date, :edition, :carrier, 'published')"
        ),
        {
            "id": manifestation_id,
            "statement": statement,
            "date": mapped.publication_date,
            "edition": mapped.edition_statement,
            "carrier": mapped.carrier_type,
        },
    )
    executor.execute(
        text(
            "insert into public.expression_manifestation "
            "(expression_entity_id, manifestation_entity_id) values (:e, :m)"
        ),
        {"e": expression_id, "m": manifestation_id},
    )

    # Authors. `100` is the main entry, `700` the added ones, and both are
    # authorship -- the role travels with the relation so "çeviren" is not lost.
    for author in mapped.authors:
        agent_id = _agent_for(executor, author.name, "person")

        executor.execute(
            text(
                "insert into public.work_agent_relation "
                "(work_entity_id, agent_entity_id, role) "
                "values (:work, :agent, :role)"
            ),
            {
                "work": work_id,
                "agent": agent_id,
                "role": author.role or ("author" if author.main else "contributor"),
            },
        )

    # The publisher, as an authority record rather than a string, so that "which
    # libraries hold this publisher's books" stays answerable.
    if mapped.publisher:
        publisher_id = _agent_for(executor, mapped.publisher, "publisher")

        executor.execute(
            text(
                "insert into public.manifestation_agent_relation "
                "(manifestation_entity_id, agent_entity_id, role) "
                "values (:manifestation, :agent, 'publisher')"
            ),
            {"manifestation": manifestation_id, "agent": publisher_id},
        )

    for scheme, values in (("ISBN", mapped.isbn), ("ISSN", mapped.issn)):
        for value in values:
            executor.execute(
                text(
                    "insert into public.identifiers "
                    "(id, entity_id, scheme, value, preferred, created_at) "
                    "values (:id, :entity, :scheme, :value, true, now())"
                ),
                {
                    "id": uuid7(),
                    "entity": manifestation_id,
                    "scheme": scheme,
                    "value": value,
                },
            )

    return {
        "work_entity_id": work_id,
        "expression_entity_id": expression_id,
        "manifestation_entity_id": manifestation_id,
    }


def _write_holding(executor, mapped: MappedRecord, ids: Mapping) -> Any:
    """Place a copy in the library the record names, if we know which that is.

    `local_holding_key` is the control number: a library's own key for the record
    is exactly what `001` is, and it is unique per library, which is what the
    constraint requires.
    """

    branch = resolve_branch(executor, mapped.library_code.raw)

    if branch is None:
        return None

    existing = executor.execute(
        text(
            "select id from tenant.holdings "
            "where tenant_id = :tenant and branch_id = :branch "
            "  and manifestation_entity_id = :manifestation"
        ),
        {
            "tenant": branch["tenant_id"],
            "branch": branch["id"],
            "manifestation": ids["manifestation_entity_id"],
        },
    ).scalar()

    if existing is not None:
        return None

    holding_id = uuid7()

    executor.execute(
        text(
            "insert into tenant.holdings "
            "(id, tenant_id, branch_id, holding_type, local_holding_key, "
            " call_number, manifestation_entity_id, status, created_at, updated_at) "
            "values (:id, :tenant, :branch, 'physical', :key, :call_number, "
            "        :manifestation, 'active', now(), now())"
        ),
        {
            "id": holding_id,
            "tenant": branch["tenant_id"],
            "branch": branch["id"],
            "key": mapped.control_number or str(holding_id)[:12],
            "call_number": mapped.call_number,
            "manifestation": ids["manifestation_entity_id"],
        },
    )

    return holding_id


def ingest(
    executor,
    data: bytes,
    *,
    source_code: str,
    source_name: str,
    limit: int | None = None,
) -> Mapping:
    """Read a MARC file and write what it says. Returns the report.

    The report is the point. A run that says "42,318 records" and nothing else
    proves nothing; this one says how many could not be read, and why, grouped by
    the field that failed.
    """

    source_id = executor.execute(
        text("select id from public.source_systems where code = :code"),
        {"code": source_code},
    ).scalar()

    if source_id is None:
        source_id = uuid7()

        executor.execute(
            text(
                "insert into public.source_systems "
                "(id, code, name, system_type, trust_level, license, attribution, "
                " base_url, is_active, created_at) "
                "values (:id, :code, :name, 'tenant', 80, 'internal', :attr, '', "
                "        true, now())"
            ),
            {
                "id": source_id,
                "code": source_code,
                "name": source_name,
                "attr": source_name,
            },
        )

    batch_id = uuid7()

    executor.execute(
        text(
            "insert into public.ingestion_batches "
            "(id, source_system, status, total, created, updated, unchanged, failed, "
            " started_at, created_at) "
            "values (:id, :source, 'running', 0, 0, 0, 0, 0, now(), now())"
        ),
        {"id": batch_id, "source": source_code},
    )

    total = created = holdings = unchanged = failed = 0
    problems: dict = {}
    examples: list = []
    unreadable: list = []

    try:
        for record in parse_records(data, strict=False):
            if limit is not None and total >= limit:
                break

            total += 1

            try:
                mapped = map_record(record)
            except Exception as error:  # noqa: BLE001 - the reason is the report
                failed += 1
                unreadable.append(f"{type(error).__name__}: {str(error)[:120]}")
                continue

            for problem in mapped.problems:
                problems[problem] = problems.get(problem, 0) + 1

            if not mapped.usable:
                failed += 1

                if len(examples) < 10:
                    examples.append(f"okunamadi: {mapped.problems[0] if mapped.problems else 'baslik yok'}")

                continue

            existing = None
            marc_identifier = None

            if mapped.control_number:
                # MARC 001 is assigned by a library, not globally. Qualifying it
                # with the stable source-system id prevents another library's
                # coincidentally identical local key from suppressing this row.
                marc_identifier = f"{source_id}:{mapped.control_number}"
                existing = executor.execute(
                    text(
                        "select em.manifestation_entity_id from public.works w "
                        "join public.identifiers i on i.entity_id = w.entity_id "
                        "join public.work_expression we on we.work_entity_id = w.entity_id "
                        "join public.expression_manifestation em "
                        "  on em.expression_entity_id = we.expression_entity_id "
                        "where i.scheme = 'MARC' and i.value = :value limit 1"
                    ),
                    {"value": marc_identifier},
                ).scalar()

            if existing is not None:
                unchanged += 1

                # The first pass may have lacked a resolvable 852 branch. Once
                # branch metadata is corrected, replaying the file can complete
                # the holding without duplicating the bibliographic record.
                if mapped.gives_a_holding:
                    if _write_holding(
                        executor,
                        mapped,
                        {"manifestation_entity_id": existing},
                    ) is not None:
                        holdings += 1

                continue

            ids = _write_record(executor, mapped)
            created += 1

            # The control number as an identifier, which is what makes a second
            # run of the same file recognise the record instead of duplicating it.
            if mapped.control_number:
                executor.execute(
                    text(
                        "insert into public.identifiers "
                        "(id, entity_id, scheme, value, preferred, created_at) "
                        "values (:id, :entity, 'MARC', :value, false, now())"
                    ),
                    {
                        "id": uuid7(),
                        "entity": ids["work_entity_id"],
                        "value": marc_identifier,
                    },
                )

            if mapped.gives_a_holding:
                if _write_holding(executor, mapped, ids) is not None:
                    holdings += 1

    except MarcError as error:
        failed += 1
        unreadable.append(f"MarcError: {str(error)[:160]}")

    report = {
        "batch_id": str(batch_id),
        "source_system": source_code,
        "total": total,
        "created": created,
        "holdings": holdings,
        "unchanged": unchanged,
        "failed": failed,
        # Named and counted, so the answer to "why 416" is a list rather than a
        # shrug.
        "problems": dict(sorted(problems.items(), key=lambda kv: -kv[1])),
        "examples": examples,
        "unreadable": unreadable[:10],
    }

    executor.execute(
        text(
            "update public.ingestion_batches "
            "set status = 'finished', total = :total, created = :created, "
            "    updated = :updated, unchanged = :unchanged, failed = :failed, "
            "    finished_at = now(), report = cast(:report as jsonb) "
            "where id = :id"
        ),
        {
            "id": batch_id,
            "total": total,
            "created": created,
            # Not the holding count. `updated` means records that already existed
            # and changed, and nothing here updates a record yet -- the first
            # version of this wrote the holdings into it, which would have made
            # the column mean two different things depending on who read it.
            "updated": 0,
            "unchanged": unchanged,
            "failed": failed,
            # Stored, not only returned. The operator reads the response once and
            # closes the tab; the reason a block of records did not arrive has to
            # outlive that.
            "report": json.dumps(report, ensure_ascii=False),
        },
    )

    return report
