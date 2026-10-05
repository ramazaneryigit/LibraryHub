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

import base64
import hashlib
import json
import math
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import Float, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.types import Uuid

from ..core.text import normalize_text

__all__ = [
    "consume",
    "decode_cursor",
    "documents",
    "encode_cursor",
    "index",
    "reindex",
    "search",
    "search_page",
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
        return {"events": 0, "documents": 0, "document_ids": []}

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

    return {
        "events": len(events),
        "documents": documents_written,
        "document_ids": sorted(str(entity_id) for entity_id in affected),
    }


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


MATCHED_WORKS = """
select unnest(d.work_ids) as work_id,
       max(similarity(d.body, :probe)) as score
from public.search_documents d
where cast(:semantic_mode as boolean) = false
  and d.body like :pattern
  and (
      cast(:search_field as text) is null
      or cast(:search_field as text) = 'all'
      or (cast(:search_field as text) = 'title' and d.entity_type = 'WORK')
      or (cast(:search_field as text) = 'author' and d.entity_type = 'PERSON')
      or (cast(:search_field as text) = 'publisher' and d.entity_type = 'ORGANIZATION')
      or (cast(:search_field as text) = 'inventory' and d.entity_type = 'MANIFESTATION')
      or (
          cast(:search_field as text) in ('isbn', 'issn', 'doi', 'orcid')
          and exists (
              select 1 from public.identifiers i
              where i.entity_id = d.entity_id
                and upper(i.scheme) = upper(cast(:identifier_scheme as text))
                and i.value ilike :raw_pattern
          )
      )
  )
group by 1

union all

select unnest(d.work_ids) as work_id, max(candidate.score)::real as score
from unnest(
    cast(:semantic_entity_ids as uuid[]),
    cast(:semantic_scores as real[])
) as candidate(entity_id, score)
join public.search_documents d on d.entity_id = candidate.entity_id
where cast(:semantic_mode as boolean) = true
  and (
      cast(:search_field as text) is null
      or cast(:search_field as text) = 'all'
      or (cast(:search_field as text) = 'title' and d.entity_type = 'WORK')
      or (cast(:search_field as text) = 'author' and d.entity_type = 'PERSON')
      or (cast(:search_field as text) = 'publisher' and d.entity_type = 'ORGANIZATION')
      or (cast(:search_field as text) = 'inventory' and d.entity_type = 'MANIFESTATION')
      or (
          cast(:search_field as text) in ('isbn', 'issn', 'doi', 'orcid')
          and exists (
              select 1 from public.identifiers i
              where i.entity_id = d.entity_id
                and upper(i.scheme) = upper(cast(:identifier_scheme as text))
                and i.value ilike :raw_pattern
          )
      )
  )
group by 1

union all

select w.entity_id, 1.0::real
from public.works w
where cast(:search_field as text) = 'university'
  and exists (
      select 1
      from public.work_expression we
      join public.expression_manifestation em
        on em.expression_entity_id = we.expression_entity_id
      join public.holdings_compat h
        on h.manifestation_entity_id = em.manifestation_entity_id
      join control.tenants t on t.id = h.tenant_id
      where we.work_entity_id = w.entity_id
        and t.display_name ilike :raw_pattern
  )
"""

FILTERED_WORKS = """
select m.work_id, m.score
from matched m
join public.works w on w.entity_id = m.work_id
where (cast(:work_type as text) is null or w.work_type = cast(:work_type as text))
  and (
      cast(:language as text) is null
      or exists (
          select 1
          from public.work_expression we
          join public.expressions e on e.entity_id = we.expression_entity_id
          where we.work_entity_id = m.work_id
            and e.language = cast(:language as text)
      )
  )
  and (
      cast(:year as text) is null
      or exists (
          select 1
          from public.work_expression we
          join public.expression_manifestation em
            on em.expression_entity_id = we.expression_entity_id
          join public.manifestations manifestation
            on manifestation.entity_id = em.manifestation_entity_id
          where we.work_entity_id = m.work_id
            and manifestation.publication_date ~ '^[0-9]{4}'
            and left(manifestation.publication_date, 4) = cast(:year as text)
      )
  )
  and (
      cast(:library_id as uuid) is null
      or exists (
          select 1
          from public.work_expression we
          join public.expression_manifestation em
            on em.expression_entity_id = we.expression_entity_id
          join public.holdings_compat h
            on h.manifestation_entity_id = em.manifestation_entity_id
          where we.work_entity_id = m.work_id
            and h.tenant_id = cast(:library_id as uuid)
      )
  )
  and (
      cast(:subject_id as uuid) is null
      or exists (
          select 1
          from public.entity_relation er
          where er.subject_entity_id = m.work_id
            and er.object_entity_id = cast(:subject_id as uuid)
            and er.predicate = 'has_subject'
      )
  )
"""


FACETS = """
with matched as (
    {matched_works}
), facets as (
    select 'work_type' as facet, w.work_type::text as value,
           w.work_type::text as label, count(distinct m.work_id) as count
    from matched m
    join public.works w on w.entity_id = m.work_id
    where w.work_type is not null and btrim(w.work_type) <> ''
    group by w.work_type

    union all

    select 'language', e.language::text, e.language::text,
           count(distinct m.work_id)
    from matched m
    join public.work_expression we on we.work_entity_id = m.work_id
    join public.expressions e on e.entity_id = we.expression_entity_id
    where e.language is not null and btrim(e.language) <> ''
    group by e.language

    union all

    select 'year', left(manifestation.publication_date, 4),
           left(manifestation.publication_date, 4), count(distinct m.work_id)
    from matched m
    join public.work_expression we on we.work_entity_id = m.work_id
    join public.expression_manifestation em
      on em.expression_entity_id = we.expression_entity_id
    join public.manifestations manifestation
      on manifestation.entity_id = em.manifestation_entity_id
    where manifestation.publication_date ~ '^[0-9]{4}'
    group by left(manifestation.publication_date, 4)

    union all

    select 'library', h.tenant_id::text, t.display_name,
           count(distinct m.work_id)
    from matched m
    join public.work_expression we on we.work_entity_id = m.work_id
    join public.expression_manifestation em
      on em.expression_entity_id = we.expression_entity_id
    join public.holdings_compat h
      on h.manifestation_entity_id = em.manifestation_entity_id
    join control.tenants t on t.id = h.tenant_id
    group by h.tenant_id, t.display_name

    union all

    select 'subject', c.entity_id::text, c.preferred_label,
           count(distinct m.work_id)
    from matched m
    join public.entity_relation er
      on er.subject_entity_id = m.work_id and er.predicate = 'has_subject'
    join public.concepts c on c.entity_id = er.object_entity_id
    group by c.entity_id, c.preferred_label
)
select facet, value, label, count
from facets
order by facet, count desc, label, value
""".replace("{matched_works}", MATCHED_WORKS)


TENANT_TOTALS = """
select t.id::text as value, t.display_name as label,
       count(distinct h.holding_id) as count
from control.tenants t
join public.holdings_compat h on h.tenant_id = t.id
where t.status = 'active'
group by t.id, t.display_name
order by count desc, t.display_name
"""


def _cursor_context(normalized: str, filters: Mapping[str, Any]) -> str:
    rendered = json.dumps(
        [normalized, {key: str(value) if value is not None else None for key, value in filters.items()}],
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]


def encode_cursor(score: float, work_id, context: str = "") -> str:
    payload = json.dumps(
        {"score": float(score), "work_id": str(work_id), "context": context},
        separators=(",", ":"),
    ).encode("utf-8")

    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str, context: str = "") -> tuple[float, uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        score = float(payload["score"])
        work_id = uuid.UUID(payload["work_id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("Invalid search cursor") from error

    if not math.isfinite(score):
        raise ValueError("Invalid search cursor score")

    if payload.get("context") != context:
        raise ValueError("Search cursor does not match this query and its filters")

    return score, work_id


def search_page(
    executor,
    probe: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    work_type: str | None = None,
    language: str | None = None,
    year: str | None = None,
    library_id=None,
    subject_id=None,
    search_field: str | None = None,
    semantic_matches: list[Mapping[str, Any]] | None = None,
) -> dict:
    """One stable keyset page, its exact total, and facets for the query."""

    normalized = normalize_text(probe)

    if not normalized:
        return {
            "work_ids": [],
            "total": 0,
            "has_more": False,
            "next_cursor": None,
            "facets": {name: [] for name in ("work_type", "language", "year", "library", "subject")},
            "institutions": [],
        }

    filters = {
        "work_type": work_type,
        "language": language,
        "year": year,
        "library_id": library_id,
        "subject_id": subject_id,
        "search_field": search_field,
        "semantic_mode": semantic_matches is not None,
    }
    context = _cursor_context(normalized, filters)
    cursor_values = decode_cursor(cursor, context) if cursor else (None, None)
    identifier_schemes = {
        "isbn": "ISBN",
        "issn": "ISSN",
        "doi": "DOI",
        "orcid": "ORCID",
    }
    semantic_matches = semantic_matches or []
    parameters = {
        "probe": normalized,
        "pattern": f"%{normalized}%",
        "raw_pattern": f"%{probe.strip()}%",
        "identifier_scheme": identifier_schemes.get(search_field),
        "semantic_entity_ids": [uuid.UUID(str(match["entity_id"])) for match in semantic_matches],
        "semantic_scores": [float(match["score"]) for match in semantic_matches],
        **filters,
    }

    cte = f"with matched as ({MATCHED_WORKS}), filtered as ({FILTERED_WORKS}) "

    def typed_statement(sql: str) -> TextClause:
        return text(sql).bindparams(
            bindparam("semantic_entity_ids", type_=ARRAY(Uuid)),
            bindparam("semantic_scores", type_=ARRAY(Float)),
        )

    total = executor.execute(
        typed_statement(cte + "select count(*) from filtered"),
        parameters,
    ).scalar() or 0

    facet_rows = executor.execute(typed_statement(FACETS), parameters).mappings().all()
    institution_rows = executor.execute(text(TENANT_TOTALS)).mappings().all()
    facets = {name: [] for name in ("work_type", "language", "year", "library", "subject")}

    for row in facet_rows:
        facets[row["facet"]].append({
            "value": row["value"],
            "label": row["label"],
            "count": row["count"],
        })

    page_rows = executor.execute(
        typed_statement(
            cte
            + "select f.work_id, f.score from filtered f "
            + "where (cast(:cursor_score as double precision) is null "
            + "   or f.score < cast(:cursor_score as double precision) "
            + "   or (f.score = cast(:cursor_score as double precision) "
            + "       and f.work_id > cast(:cursor_work_id as uuid))) "
            + "order by f.score desc, f.work_id "
            + "limit :page_limit"
        ),
        {
            **parameters,
            "cursor_score": cursor_values[0],
            "cursor_work_id": cursor_values[1],
            "page_limit": limit + 1,
        },
    ).all()

    has_more = len(page_rows) > limit
    page_rows = page_rows[:limit]
    next_cursor = None

    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_cursor(last[1], last[0], context)

    return {
        "work_ids": [row[0] for row in page_rows],
        "total": total,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "facets": facets,
        "institutions": [
            {"value": row["value"], "label": row["label"], "count": row["count"]}
            for row in institution_rows
        ],
    }


def search(executor, probe: str, limit: int = 50) -> list:
    """Backward-compatible first-page search for existing internal callers."""

    return search_page(executor, probe, limit=limit)["work_ids"]


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
