"""Reading the catalogue back out as MARC.

The other half of the promise made in `docs/veri-toplama-plani.md`: an
institution's first question before handing over a collection is whether it can
get it back, and until this exists the answer is "the codec works but there is no
button", which is worse than nothing because it sounds like it works.

What "back" means
-----------------
Not an exact copy of the file they sent. Their records were merged into a shared
catalogue, and that is the point of the thing -- two libraries holding one book
produce one work and two holdings, not two works. What comes back is therefore
**the bibliographic records of the manifestations this library holds**, which is
what a library can re-import into its own system. The distinction is written down
rather than glossed, because "you get your data back" and "you get your file back"
are different sentences.

Scoping
-------
A library exports its own holdings. Through `tenant.holdings` with the tenant
stated, because the export runs as the operator for the same reason the ingest
does: it has to reach across the planes, and a tenant session can only see one.
"""

from __future__ import annotations

from typing import Iterator, Mapping

from sqlalchemy import text

from ..core.marc_mapping import ItemRef, MappedAuthor, MappedRecord, NormalizedCode

__all__ = ["records_for_tenant"]


# The base rows: one per manifestation this library holds.
BASE = """
select distinct on (m.entity_id)
    m.entity_id            as manifestation_entity_id,
    m.publication_statement,
    m.publication_date,
    m.edition_statement,
    m.carrier_type,
    m.extent,
    m.notes,
    w.entity_id            as work_entity_id,
    w.canonical_title,
    w.original_title,
    e.language,
    h.local_holding_key,
    h.call_number,
    b.code                 as branch_code,
    b.name                 as branch_name
from tenant.holdings h
join public.manifestations m on m.entity_id = h.manifestation_entity_id
join public.expression_manifestation em on em.manifestation_entity_id = m.entity_id
join public.work_expression we on we.expression_entity_id = em.expression_entity_id
join public.works w on w.entity_id = we.work_entity_id
left join public.expressions e on e.entity_id = em.expression_entity_id
left join control.branches b on b.id = h.branch_id
where h.tenant_id = :tenant_id
  and h.manifestation_entity_id is not null
order by m.entity_id
limit :limit
"""


AUTHORS = """
select r.work_entity_id, p.canonical_name, r.role
from public.work_agent_relation r
join public.persons p on p.entity_id = r.agent_entity_id
where r.work_entity_id = any(:work_ids)
order by r.role nulls last, p.canonical_name
"""


IDENTIFIERS = """
select i.entity_id, i.scheme, i.value
from public.identifiers i
where i.entity_id = any(:entity_ids)
  and i.scheme in ('ISBN', 'ISSN')
order by i.scheme, i.value
"""


SUBJECTS = """
select er.subject_entity_id as work_entity_id,
       c.preferred_label
from public.entity_relation er
join public.concepts c on c.entity_id = er.object_entity_id
where er.predicate = 'has_subject'
  and er.subject_entity_id = any(:work_ids)
order by c.preferred_label
"""


ITEMS = """
select h.manifestation_entity_id, i.barcode, i.shelfmark
from tenant.items i
join tenant.holdings h on h.id = i.holding_id
where h.tenant_id = :tenant_id
  and h.manifestation_entity_id = any(:entity_ids)
order by i.barcode nulls last
"""


def _group(rows, key) -> dict:
    out: dict = {}

    for row in rows:
        out.setdefault(row[key], []).append(row)

    return out


def records_for_tenant(
    executor,
    tenant_id,
    *,
    limit: int = 10_000,
) -> Iterator[MappedRecord]:
    """Every bibliographic record this library holds, as MARC-ready records."""

    bases = executor.execute(
        text(BASE),
        {"tenant_id": tenant_id, "limit": limit},
    ).mappings().all()

    if not bases:
        return

    work_ids = [row["work_entity_id"] for row in bases]
    manifestation_ids = [row["manifestation_entity_id"] for row in bases]

    # Four queries rather than one with four joins: a work with three authors and
    # two subjects fans out to six rows under a single join, and the export would
    # then write the title six times.
    authors = _group(
        executor.execute(text(AUTHORS), {"work_ids": work_ids}).mappings().all(),
        "work_entity_id",
    )

    identifiers = _group(
        executor.execute(
            text(IDENTIFIERS),
            {"entity_ids": manifestation_ids},
        ).mappings().all(),
        "entity_id",
    )

    subjects = _group(
        executor.execute(text(SUBJECTS), {"work_ids": work_ids}).mappings().all(),
        "work_entity_id",
    )

    items = _group(
        executor.execute(
            text(ITEMS),
            {"tenant_id": tenant_id, "entity_ids": manifestation_ids},
        ).mappings().all(),
        "manifestation_entity_id",
    )

    for row in bases:
        work_id = row["work_entity_id"]
        manifestation_id = row["manifestation_entity_id"]

        isbn = [
            entry["value"]
            for entry in identifiers.get(manifestation_id, [])
            if entry["scheme"] == "ISBN"
        ]
        issn = [
            entry["value"]
            for entry in identifiers.get(manifestation_id, [])
            if entry["scheme"] == "ISSN"
        ]

        yield MappedRecord(
            # `001` carries what the library itself called the record, so a
            # re-import into their own system lands on the same key it came from.
            control_number=row["local_holding_key"],
            title=row["canonical_title"],
            original_title=row["original_title"],
            authors=[
                MappedAuthor(
                    name=entry["canonical_name"],
                    role=entry["role"],
                    main=index == 0,
                )
                for index, entry in enumerate(authors.get(work_id, []))
            ],
            isbn=isbn,
            issn=issn,
            language=row["language"],
            publication_statement=row["publication_statement"],
            publication_date=row["publication_date"],
            edition_statement=row["edition_statement"],
            carrier_type=row["carrier_type"],
            extent=row["extent"],
            notes=row["notes"],
            subjects=[entry["preferred_label"] for entry in subjects.get(work_id, [])],
            call_number=row["call_number"],
            library_code=(
                NormalizedCode(
                    raw=row["branch_code"],
                    normalized=row["branch_code"],
                )
                if row["branch_code"]
                else None
            ),
            items=[
                ItemRef(barcode=entry["barcode"], shelfmark=entry["shelfmark"])
                for entry in items.get(manifestation_id, [])
            ],
        )
