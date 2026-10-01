"""An academician's profile, bound to a person through ORCID.

The account points at a `persons` entity (`control.users.subject_entity_id`, added
in `c9f3a7e15b28`), and the binding is made through an ORCID iD -- because ORCID is
an authority the person maintains themselves, so it is the one identifier we can
ask them for and check the shape of.

What is *not* claimed here
--------------------------
Validating an iD's check digit proves it was typed correctly. It does not prove
whoever signed in owns it. That needs ORCID OAuth, and until that exists a binding
made this way is a claim by the person, not a verified fact. The distinction is
written down rather than glossed, because the alternative is a system that looks
like it verified something and did not.

Creating a person
-----------------
If no `persons` entity carries the ORCID, one is created. That is the only place
this module writes on behalf of somebody else, and it is deliberate: an
academician with no record in the catalogue has to be able to make one, or the
profile has nothing to open.
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text

from ..core.ids import uuid7
from ..core.orcid import normalize_orcid
from ..core.text import normalize_text

__all__ = [
    "bind_orcid",
    "libraries_holding",
    "profile",
    "profile_works",
]


def _person_for_orcid(executor, orcid: str) -> Any:
    return executor.execute(
        text(
            "select i.entity_id from public.identifiers i "
            "where i.scheme = 'ORCID' and i.value = :orcid"
        ),
        {"orcid": orcid},
    ).scalar()


def bind_orcid(executor, user, orcid: str, display_name: str | None = None) -> Mapping:
    """Point this account at the person its ORCID belongs to.

    Returns what happened rather than only succeeding, because "a new person was
    created" and "an existing person was found" are different outcomes and the
    person should see which one they got -- it is the difference between filling
    in their own profile and having just claimed somebody else's.
    """

    canonical = normalize_orcid(orcid)

    if canonical is None:
        raise ValueError(
            "ORCID iD geçersiz: on altı haneli olmalı ve son hanesi kontrol "
            "basamağı olmalı (örn. 0000-0002-1825-0097)."
        )

    person_id = _person_for_orcid(executor, canonical)
    created = False

    if person_id is None:
        name = (display_name or "").strip()

        if not name:
            raise ValueError(
                "Bu ORCID katalogda yok. Kişi kaydı oluşturmak için bir ad "
                "gerekli."
            )

        person_id = uuid7()
        created = True

        # `entities` first, then the subtype. The subtype triggers are deferred,
        # but this order has already cost one debugging session (§0.19).
        executor.execute(
            text(
                "insert into public.entities (id, entity_type, created_at, updated_at) "
                "values (:id, 'PERSON', now(), now())"
            ),
            {"id": person_id},
        )
        executor.execute(
            text(
                "insert into public.persons (entity_id, canonical_name) "
                "values (:id, :name)"
            ),
            {"id": person_id, "name": name},
        )

        # No `nomens` row is written here on purpose. `nomens.normalized_value` is
        # maintained by an ORM event listener, and raw SQL does not fire it -- so a
        # name inserted this way would be invisible to search until something
        # corrected it, which is the trap recorded in §0.27. The person's name is
        # in `persons.canonical_name`, which is what the profile reads.

    executor.execute(
        text(
            "insert into public.identifiers "
            "(id, entity_id, scheme, value, preferred, created_at) "
            "values (:id, :entity_id, 'ORCID', :value, true, now())"
            "on conflict do nothing"
        ),
        {"id": uuid7(), "entity_id": person_id, "value": canonical},
    )

    executor.execute(
        text("update control.users set subject_entity_id = :person where id = :id"),
        {"person": person_id, "id": user.id},
    )

    # The index is built from the source tables and this person may be new, so the
    # name is searchable only after the indexer runs. Said here because otherwise
    # the next person to search for themselves finds nothing and concludes the
    # profile did not save.
    return {
        "orcid": canonical,
        "person_entity_id": person_id,
        "created": created,
        "normalized_name": normalize_text(display_name or ""),
    }


def profile(executor, user) -> Mapping:
    """The person this account speaks for, and how much of them we know."""

    if user.subject_entity_id is None:
        return {
            "bound": False,
            "orcid": None,
            "person_entity_id": None,
        }

    row = executor.execute(
        text(
            "select p.entity_id, p.canonical_name, p.given_name, p.family_name, "
            "       p.biography, "
            "       (select i.value from public.identifiers i "
            "         where i.entity_id = p.entity_id and i.scheme = 'ORCID' "
            "         limit 1) as orcid "
            "from public.persons p where p.entity_id = :id"
        ),
        {"id": user.subject_entity_id},
    ).mappings().first()

    if row is None:
        return {"bound": False, "orcid": None, "person_entity_id": None}

    return {
        "bound": True,
        "person_entity_id": str(row["entity_id"]),
        "canonical_name": row["canonical_name"],
        "given_name": row["given_name"],
        "family_name": row["family_name"],
        "biography": row["biography"],
        "orcid": row["orcid"],
    }


# A person's works, through both roads: direct authorship of a work, and
# authorship of an expression inside one. Both are authorship and a profile that
# showed only the first would hide every translated or illustrated title.
WORKS = """
select
    w.entity_id       as work_entity_id,
    w.canonical_title as title,
    (select count(distinct h.id)
       from public.expression_manifestation em
       join public.work_expression we2 on we2.expression_entity_id = em.expression_entity_id
       join tenant.holdings h on h.manifestation_entity_id = em.manifestation_entity_id
      where we2.work_entity_id = w.entity_id) as holdings,
    (select count(distinct t.id)
       from public.expression_manifestation em
       join public.work_expression we2 on we2.expression_entity_id = em.expression_entity_id
       join tenant.holdings h on h.manifestation_entity_id = em.manifestation_entity_id
       join control.branches b on b.id = h.branch_id
       join control.organizations o on o.id = b.organization_id
       join control.tenants t on t.id = o.tenant_id
      where we2.work_entity_id = w.entity_id) as libraries
from public.works w
where w.entity_id in (
    select war.work_entity_id
      from public.work_agent_relation war
     where war.agent_entity_id = :person_id
    union
    select we.work_entity_id
      from public.expression_agent_relation ear
      join public.work_expression we
        on we.expression_entity_id = ear.expression_entity_id
     where ear.agent_entity_id = :person_id
)
order by libraries desc, w.canonical_title
limit :limit
"""


def profile_works(executor, user, *, limit: int = 200) -> list[Mapping]:
    if user.subject_entity_id is None:
        return []

    return executor.execute(
        text(WORKS),
        {"person_id": user.subject_entity_id, "limit": limit},
    ).mappings().all()


def libraries_holding(executor, work_id) -> list[Mapping]:
    """Which libraries hold one title, and which printing.

    Not scoped to the caller: which libraries hold a published book is public
    information -- it is exactly what the union catalogue is for -- and hiding it
    from the author while showing it to the publisher would be hard to justify.
    """

    return executor.execute(
        text(
            "select t.display_name as library, o.name as institution, "
            "       b.name as branch, m.publication_date as edition, "
            "       count(h.id) as holdings "
            "from public.expression_manifestation em "
            "join public.work_expression we "
            "  on we.expression_entity_id = em.expression_entity_id "
            "join public.manifestations m on m.entity_id = em.manifestation_entity_id "
            "join tenant.holdings h on h.manifestation_entity_id = m.entity_id "
            "join control.branches b on b.id = h.branch_id "
            "join control.organizations o on o.id = b.organization_id "
            "join control.tenants t on t.id = o.tenant_id "
            "where we.work_entity_id = :work_id "
            "group by t.display_name, o.name, b.name, m.publication_date "
            "order by t.display_name, m.publication_date"
        ),
        {"work_id": work_id},
    ).mappings().all()
