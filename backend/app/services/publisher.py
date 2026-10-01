"""What a publisher can see, and what it can say.

The question a publisher actually has is "who has my books", and the union
catalogue has been able to answer it since Aşama 3 without a single new row: a
title reaches a library through

    collective_agents (agent_type='publisher') <- manifestation_agent_relation
      -> manifestation -> expression_manifestation -> work_expression -> work
      <- expression_manifestation <- manifestation <- holdings -> branches
      -> organizations -> tenants

Nothing here is derived or cached. It is the same chain the library workspace
walks, read from the other end.

Declaring a title reuses `isbn.declare_publication` rather than writing the chain
again: a publisher announcing a book and an agency announcing one are the same
act, and two implementations of it would eventually disagree about what a
publication record contains.
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text

__all__ = [
    "library_report",
    "publisher_titles",
    "summary",
]


# Which libraries hold which of this publisher's titles. Holdings, not items: a
# library that has catalogued a title but not yet barcoded a copy still *holds*
# it, and reporting items would hide exactly the libraries in the middle of
# processing.
TITLES = """
select
    w.entity_id            as work_entity_id,
    w.canonical_title      as title,
    (select count(distinct m2.entity_id)
       from public.expression_manifestation em2
       join public.work_expression we2 on we2.expression_entity_id = em2.expression_entity_id
       join public.manifestations m2 on m2.entity_id = em2.manifestation_entity_id
       join public.manifestation_agent_relation mar2
         on mar2.manifestation_entity_id = m2.entity_id
      where we2.work_entity_id = w.entity_id
        and mar2.agent_entity_id = :agent_id) as manifestations,
    (select count(distinct h.id)
       from public.expression_manifestation em3
       join public.work_expression we3 on we3.expression_entity_id = em3.expression_entity_id
       join tenant.holdings h on h.manifestation_entity_id = em3.manifestation_entity_id
      where we3.work_entity_id = w.entity_id) as holdings,
    (select count(distinct t.id)
       from public.expression_manifestation em4
       join public.work_expression we4 on we4.expression_entity_id = em4.expression_entity_id
       join tenant.holdings h4 on h4.manifestation_entity_id = em4.manifestation_entity_id
       join control.branches b4 on b4.id = h4.branch_id
       join control.organizations o4 on o4.id = b4.organization_id
       join control.tenants t on t.id = o4.tenant_id
      where we4.work_entity_id = w.entity_id) as libraries
from public.works w
where exists (
    select 1
      from public.work_expression we
      join public.expression_manifestation em on em.expression_entity_id = we.expression_entity_id
      join public.manifestation_agent_relation mar
        on mar.manifestation_entity_id = em.manifestation_entity_id
     where we.work_entity_id = w.entity_id
       and mar.agent_entity_id = :agent_id
)
order by libraries desc, w.canonical_title
limit :limit
"""


HOLDERS = """
select
    t.display_name   as library,
    o.name           as institution,
    b.name           as branch,
    m.publication_date as edition,
    count(h.id)      as holdings
from public.expression_manifestation em
join public.work_expression we on we.expression_entity_id = em.expression_entity_id
join public.manifestations m on m.entity_id = em.manifestation_entity_id
join tenant.holdings h on h.manifestation_entity_id = m.entity_id
join control.branches b on b.id = h.branch_id
join control.organizations o on o.id = b.organization_id
join control.tenants t on t.id = o.tenant_id
where we.work_entity_id = :work_id
  and exists (
      select 1 from public.manifestation_agent_relation mar
       where mar.manifestation_entity_id = m.entity_id
         and mar.agent_entity_id = :agent_id
  )
group by t.display_name, o.name, b.name, m.publication_date
order by t.display_name, m.publication_date
"""


def _require_agent(user) -> Any:
    if user.subject_entity_id is None:
        raise ValueError(
            "Bu hesap bir yayinevi kaydina bagli degil. "
            "Hesabi bir otorite kaydina baglamadan 'benim kitaplarim' sorusu "
            "cevaplanamaz."
        )

    return user.subject_entity_id


def publisher_titles(executor, user, *, limit: int = 200) -> list[Mapping]:
    """This publisher's titles, most widely held first.

    Ordered by how many libraries hold it, because that is the number the
    publisher opened the screen for.
    """

    return executor.execute(
        text(TITLES),
        {"agent_id": _require_agent(user), "limit": limit},
    ).mappings().all()


def library_report(executor, user, work_id) -> list[Mapping]:
    """Which libraries hold one title, and which printing of it."""

    return executor.execute(
        text(HOLDERS),
        {"agent_id": _require_agent(user), "work_id": work_id},
    ).mappings().all()


def summary(executor, user) -> Mapping:
    """The four numbers a publisher wants on arrival."""

    agent_id = _require_agent(user)

    return executor.execute(
        text(
            """
            select
                (select count(distinct we.work_entity_id)
                   from public.work_expression we
                   join public.expression_manifestation em
                     on em.expression_entity_id = we.expression_entity_id
                   join public.manifestation_agent_relation mar
                     on mar.manifestation_entity_id = em.manifestation_entity_id
                  where mar.agent_entity_id = :agent_id) as titles,
                (select count(distinct m.entity_id)
                   from public.manifestation_agent_relation mar
                   join public.manifestations m on m.entity_id = mar.manifestation_entity_id
                  where mar.agent_entity_id = :agent_id) as manifestations,
                (select count(distinct h.id)
                   from public.manifestation_agent_relation mar
                   join tenant.holdings h on h.manifestation_entity_id = mar.manifestation_entity_id
                  where mar.agent_entity_id = :agent_id) as holdings,
                (select count(distinct t.id)
                   from public.manifestation_agent_relation mar
                   join tenant.holdings h on h.manifestation_entity_id = mar.manifestation_entity_id
                   join control.branches b on b.id = h.branch_id
                   join control.organizations o on o.id = b.organization_id
                   join control.tenants t on t.id = o.tenant_id
                  where mar.agent_entity_id = :agent_id) as libraries,
                (select count(*)
                   from public.manifestations m
                   join public.manifestation_agent_relation mar
                     on mar.manifestation_entity_id = m.entity_id
                  where mar.agent_entity_id = :agent_id
                    and m.publication_status in ('announced', 'in_press')) as upcoming
            """
        ),
        {"agent_id": agent_id},
    ).mappings().one()
