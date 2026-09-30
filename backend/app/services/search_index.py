"""The derived search index: what it holds, how it is fed, how it is rebuilt.

§9.3: the index is never the source of truth, and it must always be fully
reproducible from PostgreSQL. Everything here exists to make that true and to
make it checkable -- `run_scale_checks.py` rebuilds the whole index and compares
it against the incrementally maintained one, so a divergence is a failed check
rather than a search result that is quietly wrong.

One document per entity, holding only its own text
--------------------------------------------------
A work's document holds the work's title. A person's document holds the person's
names. A search matches documents and unions the `work_ids` each one carries, so
an author-name match finds the person's document and resolves to their works
without the works themselves having to repeat the author's name.

That is what keeps the outbox mapping one-to-one. If a work's document repeated
its authors' names, then a nomen change would have to find and rebuild every work
that person wrote. Instead the event resolves to the person's document and stops
there.

Two callers, one definition
---------------------------
`index()` and `reindex()` both compose a document through `documents()`. There is
no second implementation to drift.

See docs/architecture-v2.md §0.31.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import TextClause
from sqlalchemy.types import Uuid

from ..core.text import normalize_text

__all__ = [
    "consume",
    "documents",
    "index",
    "reindex",
    "search",
    "stats",
]


# How a changed row resolves to the document it affects. Each query returns
# (changed id, document entity id) pairs.
#
# Items and holdings are here because a reader searches for a barcode as readily
# as a title, and a barcode belongs to the manifestation the copy is of. Nomens
# and identifiers resolve to whatever entity they describe.
RESOLUTION = {
    "works": "select entity_id, entity_id from public.works where entity_id = any(:ids)",
    "expressions": "select entity_id, entity_id from public.expressions where entity_id = any(:ids)",
    "manifestations": "select entity_id, entity_id from public.manifestations where entity_id = any(:ids)",
    "persons": "select entity_id, entity_id from public.persons where entity_id = any(:ids)",
    "collective_agents": "select entity_id, entity_id from public.collective_agents where entity_id = any(:ids)",
    "concepts": "select entity_id, entity_id from public.concepts where entity_id = any(:ids)",
    "identifiers": "select id, entity_id from public.identifiers where id = any(:ids)",
    "nomens": "select id, entity_id from public.nomens where id = any(:ids)",
    # A relation changes what belongs to what, so both ends are documents.
    "work_expression": (
        "select work_entity_id as changed, work_entity_id as document "
        "from public.work_expression where work_entity_id = any(:ids) "
        "union "
        "select expression_entity_id, expression_entity_id "
        "from public.work_expression where expression_entity_id = any(:ids)"
    ),
    "expression_manifestation": (
        "select expression_entity_id, expression_entity_id "
        "from public.expression_manifestation where expression_entity_id = any(:ids) "
        "union "
        "select manifestation_entity_id, manifestation_entity_id "
        "from public.expression_manifestation where manifestation_entity_id = any(:ids)"
    ),
    "work_agent_relation": (
        "select agent_entity_id, agent_entity_id "
        "from public.work_agent_relation where agent_entity_id = any(:ids) "
        "union "
        "select work_entity_id, work_entity_id "
        "from public.work_agent_relation where work_entity_id = any(:ids)"
    ),
    "expression_agent_relation": (
        "select agent_entity_id, agent_entity_id "
        "from public.expression_agent_relation where agent_entity_id = any(:ids) "
        "union "
        "select expression_entity_id, expression_entity_id "
        "from public.expression_agent_relation where expression_entity_id = any(:ids)"
    ),
    "manifestation_agent_relation": (
        "select agent_entity_id, agent_entity_id "
        "from public.manifestation_agent_relation where agent_entity_id = any(:ids) "
        "union "
        "select manifestation_entity_id, manifestation_entity_id "
        "from public.manifestation_agent_relation where manifestation_entity_id = any(:ids)"
    ),
    "entity_relation": (
        "select subject_entity_id, subject_entity_id "
        "from public.entity_relation where subject_entity_id = any(:ids) "
        "union "
        "select object_entity_id, object_entity_id "
        "from public.entity_relation where object_entity_id = any(:ids)"
    ),
    "entity_merges": (
        "select merged_entity_id, merged_entity_id "
        "from public.entity_merges where merged_entity_id = any(:ids) "
        "union "
        "select canonical_entity_id, canonical_entity_id "
        "from public.entity_merges where canonical_entity_id = any(:ids)"
    ),
    # A copy or a holding belongs to the manifestation (or expression) it is of.
    "holdings": (
        "select id, coalesce(manifestation_entity_id, expression_entity_id) "
        "from tenant.holdings where id = any(:ids)"
    ),
    "items": (
        "select i.id, coalesce(h.manifestation_entity_id, h.expression_entity_id) "
        "from tenant.items i join tenant.holdings h on h.id = i.holding_id "
        "where i.id = any(:ids)"
    ),
    "item_identifiers": (
        "select ii.id, coalesce(h.manifestation_entity_id, h.expression_entity_id) "
        "from tenant.item_identifiers ii "
        "join tenant.items i on i.id = ii.item_id "
        "join tenant.holdings h on h.id = i.holding_id "
        "where ii.id = any(:ids)"
    ),
}


# The document body, per entity type. One statement, so the incremental path and
# a full rebuild cannot disagree about what a document contains.
#
# `raw` is deliberately unnormalized: it is normalized in Python, by the one
# implementation of that decision. `work_ids` is what a match resolves to.
DOCUMENTS = """
select
    d.entity_id,
    d.entity_type,
    d.label,
    d.raw,
    d.work_ids
from (
    select
        w.entity_id,
        'WORK'::text as entity_type,
        w.canonical_title as label,
        concat_ws(' ',
            w.canonical_title,
            w.original_title,
            w.work_type,
            w.description,
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = w.entity_id)
        ) as raw,
        array[w.entity_id] as work_ids
    from public.works w
    where w.entity_id = any(:ids)

    union all

    select
        p.entity_id,
        'PERSON',
        p.canonical_name,
        concat_ws(' ',
            p.canonical_name, p.given_name, p.family_name, p.biography,
            (select string_agg(n.value, ' ')
               from public.nomens n where n.entity_id = p.entity_id),
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = p.entity_id)
        ),
        array(
            select war.work_entity_id
              from public.work_agent_relation war
             where war.agent_entity_id = p.entity_id
            union
            select we.work_entity_id
              from public.expression_agent_relation ear
              join public.work_expression we
                on we.expression_entity_id = ear.expression_entity_id
             where ear.agent_entity_id = p.entity_id
        )
    from public.persons p
    where p.entity_id = any(:ids)

    union all

    select
        c.entity_id,
        'CONCEPT',
        c.preferred_label,
        concat_ws(' ',
            c.preferred_label, c.definition, c.scheme,
            (select string_agg(n.value, ' ')
               from public.nomens n where n.entity_id = c.entity_id),
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = c.entity_id)
        ),
        array(
            select er.subject_entity_id
              from public.entity_relation er
             where er.object_entity_id = c.entity_id
               and er.predicate = 'has_subject'
        )
    from public.concepts c
    where c.entity_id = any(:ids)

    union all

    select
        ca.entity_id,
        'ORGANIZATION',
        ca.canonical_name,
        concat_ws(' ',
            ca.canonical_name, ca.agent_type, ca.description,
            (select string_agg(n.value, ' ')
               from public.nomens n where n.entity_id = ca.entity_id),
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = ca.entity_id)
        ),
        array(
            select we.work_entity_id
              from public.manifestation_agent_relation mar
              join public.expression_manifestation em
                on em.manifestation_entity_id = mar.manifestation_entity_id
              join public.work_expression we
                on we.expression_entity_id = em.expression_entity_id
             where mar.agent_entity_id = ca.entity_id
        )
    from public.collective_agents ca
    where ca.entity_id = any(:ids)

    union all

    select
        x.entity_id,
        'EXPRESSION',
        x.language,
        concat_ws(' ',
            x.language, x.expression_form, x.description,
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = x.entity_id),
            (select string_agg(p.canonical_name, ' ')
               from public.expression_agent_relation ear
               join public.persons p on p.entity_id = ear.agent_entity_id
              where ear.expression_entity_id = x.entity_id)
        ),
        array(
            select we.work_entity_id
              from public.work_expression we
             where we.expression_entity_id = x.entity_id
        )
    from public.expressions x
    where x.entity_id = any(:ids)

    union all

    select
        m.entity_id,
        'MANIFESTATION',
        m.publication_statement,
        concat_ws(' ',
            m.publication_statement, m.publication_date, m.edition_statement,
            m.carrier_type, m.extent, m.notes,
            (select string_agg(i.value, ' ')
               from public.identifiers i where i.entity_id = m.entity_id),
            (select string_agg(ca.canonical_name, ' ')
               from public.manifestation_agent_relation mar
               join public.collective_agents ca
                 on ca.entity_id = mar.agent_entity_id
              where mar.manifestation_entity_id = m.entity_id),
            (select string_agg(concat_ws(' ', v.barcode, v.shelfmark), ' ')
               from public.items_compat v
              where v.manifestation_entity_id = m.entity_id),
            -- Copy-level identifiers: a reader searches for a catalogue number
            -- as readily as a barcode, and the live query matches both.
            (select string_agg(ii.value, ' ')
               from public.item_identifiers ii
               join public.items_compat v2 on v2.entity_id = ii.entity_id
              where v2.manifestation_entity_id = m.entity_id)
        ),
        array(
            select we.work_entity_id
              from public.expression_manifestation em
              join public.work_expression we
                on we.expression_entity_id = em.expression_entity_id
             where em.manifestation_entity_id = m.entity_id
        )
    from public.manifestations m
    where m.entity_id = any(:ids)
) d
"""


def _typed(sql: str, *identifiers: str) -> TextClause:
    """`text()`, with the named parameters declared as arrays of UUIDs.

    Every parameter here is an `= any(:ids)` list, and the type has to say so.
    Declaring a bare `Uuid` renders `$1::UUID`, which PostgreSQL refuses to cast
    to `uuid[]` -- "cannot cast type uuid[] to uuid". The array type renders
    `$1::UUID[]`, which is what the query is asking for.
    """

    statement = text(sql)

    if identifiers:
        statement = statement.bindparams(
            *(bindparam(name, type_=ARRAY(Uuid)) for name in identifiers)
        )

    return statement


def _as_uuid(value: Any) -> Any:
    """A UUID, whether the caller or the driver supplied it.

    Raw SQL has no result processor: an id read back from a row is a UUID on
    PostgreSQL and the stored CHAR(32) on SQLite.
    """

    if value is None or isinstance(value, uuid.UUID):
        return value

    return uuid.UUID(str(value))


def documents(executor, entity_ids: Iterable) -> list[Mapping]:
    """The documents for these entities, normalized and ready to store."""

    ids = [_as_uuid(value) for value in entity_ids]

    if not ids:
        return []

    rows = executor.execute(_typed(DOCUMENTS, "ids"), {"ids": ids}).mappings().all()

    prepared = []

    for row in rows:
        body = normalize_text(row["raw"]) or ""

        prepared.append(
            {
                "entity_id": row["entity_id"],
                "entity_type": row["entity_type"],
                "label": row["label"] or "",
                "body": body,
                "work_ids": row["work_ids"] or [],
            }
        )

    return prepared


def resolve(executor, aggregate_type: str, ids: Iterable) -> list:
    """Which documents a set of changed rows affects."""

    statement = RESOLUTION.get(aggregate_type)

    if statement is None or not ids:
        return []

    values = [_as_uuid(value) for value in ids]

    rows = executor.execute(
        _typed(statement, "ids"),
        {"ids": values},
    ).all()

    # An item or a holding may resolve to nothing (a holding with no target),
    # and a relation may point at an entity the index has no document type for.
    return [row[1] for row in rows if row[1] is not None]


def index(executor, entity_ids: Iterable) -> int:
    """Rebuild these documents from the source tables."""

    prepared = documents(executor, entity_ids)

    for document in prepared:
        executor.execute(
            text(
                "insert into public.search_documents "
                "(entity_id, entity_type, label, body, work_ids, "
                " source_updated_at, indexed_at) "
                "values (:entity_id, :entity_type, :label, :body, :work_ids, "
                "        now(), now()) "
                "on conflict (entity_id) do update set "
                "  entity_type = excluded.entity_type, "
                "  label = excluded.label, "
                "  body = excluded.body, "
                "  work_ids = excluded.work_ids, "
                "  source_updated_at = now(), "
                "  indexed_at = now()"
            ),
            {
                "entity_id": document["entity_id"],
                "entity_type": document["entity_type"],
                "label": document["label"],
                "body": document["body"],
                # psycopg and sqlite3 disagree about lists; a literal array is
                # accepted by both through the text protocol.
                "work_ids": "{" + ",".join(str(v) for v in document["work_ids"]) + "}",
            },
        )

    return len(prepared)


def consume(executor, limit: int = 500) -> dict:
    """Drain unpublished outbox events into the index.

    The events are marked published in the same transaction as the documents
    they caused, so a crash between the two cannot lose a change -- which is the
    whole reason the outbox exists.
    """

    events = (
        executor.execute(
            text(
                "select id, aggregate_type, aggregate_id "
                "from public.outbox_events "
                "where published_at is null "
                "order by occurred_at "
                "limit :limit"
            ),
            {"limit": limit},
        )
        .mappings()
        .all()
    )

    if not events:
        return {"events": 0, "documents": 0}

    by_type: dict = {}

    for event in events:
        by_type.setdefault(event["aggregate_type"], []).append(event["aggregate_id"])

    affected = set()

    for aggregate_type, ids in by_type.items():
        affected.update(resolve(executor, aggregate_type, ids))

    documents_written = index(executor, affected)

    executor.execute(
        text(
            "update public.outbox_events set published_at = now() "
            "where id = any(:ids)"
        ),
        {"ids": [event["id"] for event in events]},
    )

    return {"events": len(events), "documents": documents_written}


def reindex(executor) -> int:
    """Throw the index away and build it again from PostgreSQL.

    This is the operation §9.3 requires to exist and to be tested. It reads
    nothing from the index, so whatever state the index is in -- empty, partial,
    wrong -- the answer is the same.
    """

    executor.execute(text("delete from public.search_documents"))

    work_ids = (
        executor.execute(text("select entity_id from public.works"))
        .scalars()
        .all()
    )

    # Every entity that can appear in a document: the works themselves and
    # everything the documents point at.
    entity_ids = list(work_ids)

    for statement in (
        "select entity_id from public.persons",
        "select entity_id from public.concepts",
        "select entity_id from public.collective_agents",
        "select entity_id from public.expressions",
        "select entity_id from public.manifestations",
    ):
        entity_ids.extend(executor.execute(text(statement)).scalars().all())

    return index(executor, entity_ids)


def search(executor, probe: str, limit: int = 50) -> list:
    """Works whose documents match, most specific first.

    Matching an entity's own document and resolving through `work_ids` is what
    lets a single index answer "who wrote this" and "what is this called"
    without the work repeating its authors.
    """

    normalized = normalize_text(probe)

    if not normalized:
        return []

    rows = executor.execute(
        text(
            "select unnest(work_ids) as work_id, "
            "       max(similarity(body, :probe)) as score "
            "from public.search_documents "
            "where body like :pattern "
            "group by 1 "
            "order by 2 desc, 1 "
            "limit :limit"
        ),
        {"probe": normalized, "pattern": f"%{normalized}%", "limit": limit},
    ).all()

    return [row[0] for row in rows]


def stats(executor) -> dict:
    total, with_works, indexed = executor.execute(
        text(
            "select count(*), count(*) filter (where cardinality(work_ids) > 0), "
            "max(indexed_at) from public.search_documents"
        )
    ).one()

    pending = executor.execute(
        text(
            "select count(*) from public.outbox_events where published_at is null"
        )
    ).scalar()

    return {
        "documents": total,
        "reachable": with_works,
        "indexed_at": indexed,
        "pending_events": pending,
    }
