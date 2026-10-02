"""Declaring a publication that does not exist yet.

An ISBN is assigned before a book is printed, so the agency knows about works that
no library holds, no shelf has room for, and no reader can borrow. That is the one
contribution only the agency can make, and it is why `publication_status` had to
exist first: without it a record either has to pretend the book is out, or not be
written at all.

What this creates
-----------------
Work -> Expression -> Manifestation, with the ISBN as an identifier and the
publisher as an agent. Nothing else. In particular **no holding and no item**: a
library has not acquired it, and inventing a holding so the record looks complete
would put a book on a shelf that does not exist. When a library buys it, the
holding they create is what makes it real.

The source
----------
The agency's source system is minted on first use rather than seeded by a
migration, because the agency does not exist as a participant until it first
declares something -- and a row for a participant who has never spoken would be
invented data of exactly the kind this project tries not to write.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy import text

from ..core.ids import uuid7
from ..core.text import normalize_text

__all__ = [
    "agency_source",
    "declare_publication",
    "list_declared",
]


AGENCY_CODE = "isbn-agency"


def agency_source(executor) -> Any:
    """The ISBN agency as a source system, created the first time it is needed."""

    existing = executor.execute(
        text("select id from public.source_systems where code = :code"),
        {"code": AGENCY_CODE},
    ).scalar()

    if existing is not None:
        return existing

    source_id = uuid7()

    executor.execute(
        text(
            "insert into public.source_systems "
            "(id, code, name, system_type, trust_level, license, attribution, "
            " base_url, is_active, created_at) "
            "values (:id, :code, :name, 'isbn_agency', 95, 'internal', "
            "        :attribution, '', true, now()) "
            "on conflict (code) do nothing"
        ),
        {
            "id": source_id,
            "code": AGENCY_CODE,
            # Two parameters, not one reused twice: `name` and `attribution` have
            # different types, and PostgreSQL refuses to deduce a single type for
            # a parameter that appears in both positions.
            "name": "ISBN Ajansı",
            "attribution": "ISBN Ajansı",
        },
    )

    return executor.execute(
        text("select id from public.source_systems where code = :code"),
        {"code": AGENCY_CODE},
    ).scalar()


def declare_publication(
    executor,
    *,
    title: str,
    isbn: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    publication_date: str | None = None,
    language: str | None = None,
    carrier_type: str | None = None,
    edition_statement: str | None = None,
    status: str = "announced",
) -> Mapping:
    """Create the chain and return the ids it created.

    `entities` is written before its subtype in every case. The subtype triggers
    are deferred, but the order has already cost one debugging session (§0.19) and
    is cheap to keep right.
    """

    if status not in ("announced", "in_press"):
        raise ValueError(
            "an ISBN declaration is 'announced' or 'in_press'; other statuses "
            "describe a book somebody can already hold"
        )

    work_id = uuid7()
    expression_id = uuid7()
    manifestation_id = uuid7()
    publisher_id = None

    # Work
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
            "(entity_id, canonical_title, normalized_title, created_at) "
            "values (:id, :title, :normalized, now())"
        ),
        {
            "id": work_id,
            "title": title,
            "normalized": normalize_text(title) or title.casefold(),
        },
    )

    # The author becomes an authority record and a relation, not a string in the
    # work's description.
    #
    # It used to be the description, while the MARC path created a person -- so the
    # same catalogue held two answers to "who wrote this". The export made it
    # visible: a record declared through the ISBN path came back with no author at
    # all, because there was no author to export, only a sentence.
    if author:
        from .authority_queue import agent_for

        author_id = agent_for(executor, author, "person")

        executor.execute(
            text(
                "insert into public.work_agent_relation "
                "(work_entity_id, agent_entity_id, role) "
                "values (:work, :agent, 'author')"
            ),
            {"work": work_id, "agent": author_id},
        )

    # Expression
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
        {"id": expression_id, "language": language},
    )
    executor.execute(
        text(
            "insert into public.work_expression "
            "(work_entity_id, expression_entity_id) values (:work_id, :expression_id)"
        ),
        {"work_id": work_id, "expression_id": expression_id},
    )

    # Manifestation
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
            "(entity_id, publication_date, edition_statement, carrier_type, "
            " publication_status) "
            "values (:id, :date, :edition, :carrier, :status)"
        ),
        {
            "id": manifestation_id,
            "date": publication_date,
            "edition": edition_statement,
            "carrier": carrier_type,
            "status": status,
        },
    )
    executor.execute(
        text(
            "insert into public.expression_manifestation "
            "(expression_entity_id, manifestation_entity_id) "
            "values (:expression_id, :manifestation_id)"
        ),
        {"expression_id": expression_id, "manifestation_id": manifestation_id},
    )

    # The ISBN itself. `preferred` because an ISBN is the identifier of record for
    # a manifestation -- when two sources disagree about it, this is the one the
    # agency assigned.
    if isbn:
        executor.execute(
            text(
                "insert into public.identifiers "
                "(id, entity_id, scheme, value, preferred, created_at) "
                "values (:id, :entity_id, 'ISBN', :value, true, now())"
            ),
            {"id": uuid7(), "entity_id": manifestation_id, "value": isbn},
        )

    # The publisher, as an authority record rather than a string on the
    # manifestation: "which libraries hold this publisher's books" is a question
    # the union catalogue should be able to answer, and a string cannot be joined.
    if publisher:
        publisher_id = executor.execute(
            text(
                "select entity_id from public.collective_agents "
                "where canonical_name = :name limit 1"
            ),
            {"name": publisher},
        ).scalar()

        if publisher_id is None:
            publisher_id = uuid7()

            executor.execute(
                text(
                    "insert into public.entities "
                    "(id, entity_type, created_at, updated_at) "
                    "values (:id, 'ORGANIZATION', now(), now())"
                ),
                {"id": publisher_id},
            )
            executor.execute(
                text(
                    "insert into public.collective_agents "
                    "(entity_id, canonical_name, agent_type) "
                    "values (:id, :name, 'publisher')"
                ),
                {"id": publisher_id, "name": publisher},
            )

        executor.execute(
            text(
                "insert into public.manifestation_agent_relation "
                "(manifestation_entity_id, agent_entity_id, role) "
                "values (:manifestation_id, :agent_id, 'publisher')"
            ),
            {"manifestation_id": manifestation_id, "agent_id": publisher_id},
        )

    return {
        "work_entity_id": work_id,
        "expression_entity_id": expression_id,
        "manifestation_entity_id": manifestation_id,
        "publisher_entity_id": publisher_id,
        "isbn": isbn,
        "title": title,
        "publication_status": status,
    }


def list_declared(executor, *, limit: int = 200) -> list[Mapping]:
    """What the agency has declared, newest first, with the ISBN if there is one.

    Reads the two not-yet statuses only. A publication the agency declared and
    that has since come out belongs to the catalogue, not to this list.
    """

    return executor.execute(
        text(
            "select m.entity_id as manifestation_entity_id, m.publication_status, "
            "       m.publication_date, m.carrier_type, "
            "       w.entity_id as work_entity_id, w.canonical_title, "
            "       i.value as isbn, "
            "       (select ca.canonical_name "
            "          from public.manifestation_agent_relation mar "
            "          join public.collective_agents ca "
            "            on ca.entity_id = mar.agent_entity_id "
            "         where mar.manifestation_entity_id = m.entity_id "
            "         limit 1) as publisher "
            "from public.manifestations m "
            "join public.expression_manifestation em "
            "  on em.manifestation_entity_id = m.entity_id "
            "join public.work_expression we "
            "  on we.expression_entity_id = em.expression_entity_id "
            "join public.works w on w.entity_id = we.work_entity_id "
            "left join public.identifiers i "
            "  on i.entity_id = m.entity_id and i.scheme = 'ISBN' "
            "where m.publication_status in ('announced', 'in_press') "
            "order by m.entity_id desc "
            "limit :limit"
        ),
        {"limit": limit},
    ).mappings().all()
