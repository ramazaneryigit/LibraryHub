"""What a publisher can see, and what it can say.

The question a publisher actually has is "who has my books", and the union
catalogue answers it from the chain:

    collective_agents (a publisher) <- manifestation_agent_relation
      -> manifestation -> expression_manifestation -> work_expression -> work
      <- expression_manifestation <- holdings -> tenant

Read through `public.holdings_compat`, not `tenant.holdings`.

That is not a detail. A publisher asks across every library, but `tenant.holdings`
is fail-closed per tenant and this request arrives with no tenant bound -- so the
tenant table answers with zero rows and the report is silently empty. That is
exactly what happened: the endpoints worked, the numbers were all zero, and
nothing said why. The projection is the same holdings in the global plane, and it
carries `tenant_id` and `holding_institution_entity_id`, which is why the whole
`branches -> organizations -> tenants` hop disappears. "How many libraries" is a
`count(distinct tenant_id)`.

There is no `branch` in the answer, and that is the boundary rather than a
shortcoming. A publisher needs to know that Kirikkale University holds the book,
not which of its branches does. Which branch is tenant-plane data, and a reader
looking across tenants should not have it.

Nothing here is derived or cached. It is the chain the library workspace walks,
read from the other end.
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text

__all__ = [
    "library_report",
    "publisher_titles",
    "summary",
]


# Holdings, not copies. A library that has catalogued a title but not yet barcoded
# a copy still *holds* it, and counting items would hide exactly the libraries in
# the middle of processing.
TITLES = """
select
    w.entity_id       as work_entity_id,
    w.canonical_title as title,
    (select count(distinct m2.entity_id)
       from public.expression_manifestation em2
       join public.work_expression we2
         on we2.expression_entity_id = em2.expression_entity_id
       join public.manifestations m2
         on m2.entity_id = em2.manifestation_entity_id
       join public.manifestation_agent_relation mar2
         on mar2.manifestation_entity_id = m2.entity_id
      where we2.work_entity_id = w.entity_id
        and mar2.agent_entity_id = :agent_id) as manifestations,
    (select count(distinct h3.holding_id)
       from public.expression_manifestation em3
       join public.work_expression we3
         on we3.expression_entity_id = em3.expression_entity_id
       join public.holdings_compat h3
         on h3.manifestation_entity_id = em3.manifestation_entity_id
      where we3.work_entity_id = w.entity_id) as holdings,
    (select count(distinct h4.tenant_id)
       from public.expression_manifestation em4
       join public.work_expression we4
         on we4.expression_entity_id = em4.expression_entity_id
       join public.holdings_compat h4
         on h4.manifestation_entity_id = em4.manifestation_entity_id
      where we4.work_entity_id = w.entity_id) as libraries
from public.works w
where exists (
    select 1
      from public.work_expression we
      join public.expression_manifestation em
        on em.expression_entity_id = we.expression_entity_id
      join public.manifestation_agent_relation mar
        on mar.manifestation_entity_id = em.manifestation_entity_id
     where we.work_entity_id = w.entity_id
       and mar.agent_entity_id = :agent_id
)
order by libraries desc, w.canonical_title
limit :limit
"""


# Which libraries hold one title, and which printing of it. The library name comes
# from `control.tenants`, which is readable across tenants by design; the
# institution from the authority record the projection points at.
HOLDERS = """
select
    t.display_name        as library,
    ca.canonical_name     as institution,
    m.publication_date    as edition,
    count(h.holding_id)   as holdings
from public.expression_manifestation em
join public.work_expression we
  on we.expression_entity_id = em.expression_entity_id
join public.manifestations m
  on m.entity_id = em.manifestation_entity_id
join public.holdings_compat h
  on h.manifestation_entity_id = m.entity_id
join control.tenants t
  on t.id = h.tenant_id
left join public.collective_agents ca
  on ca.entity_id = h.holding_institution_entity_id
where we.work_entity_id = :work_id
  and exists (
      select 1 from public.manifestation_agent_relation mar
       where mar.manifestation_entity_id = m.entity_id
         and mar.agent_entity_id = :agent_id
  )
group by t.display_name, ca.canonical_name, m.publication_date
order by t.display_name, m.publication_date
"""


SUMMARY = """
select
    (select count(distinct we.work_entity_id)
       from public.work_expression we
       join public.expression_manifestation em
         on em.expression_entity_id = we.expression_entity_id
       join public.manifestation_agent_relation mar
         on mar.manifestation_entity_id = em.manifestation_entity_id
      where mar.agent_entity_id = :agent_id) as titles,
    (select count(distinct mar.manifestation_entity_id)
       from public.manifestation_agent_relation mar
      where mar.agent_entity_id = :agent_id) as manifestations,
    (select count(distinct h.holding_id)
       from public.manifestation_agent_relation mar
       join public.holdings_compat h
         on h.manifestation_entity_id = mar.manifestation_entity_id
      where mar.agent_entity_id = :agent_id) as holdings,
    (select count(distinct h.tenant_id)
       from public.manifestation_agent_relation mar
       join public.holdings_compat h
         on h.manifestation_entity_id = mar.manifestation_entity_id
      where mar.agent_entity_id = :agent_id) as libraries,
    (select count(*)
       from public.manifestations m
       join public.manifestation_agent_relation mar
         on mar.manifestation_entity_id = m.entity_id
      where mar.agent_entity_id = :agent_id
        and m.publication_status in ('announced', 'in_press')) as upcoming
"""


def _agent(user) -> Any:
    """The authority record this account speaks for.

    Not a display name: answering "which titles are mine" from a name would turn a
    spelling mistake into a different publisher.
    """

    if user.subject_entity_id is None:
        raise ValueError(
            "Bu hesap bir yayinevi kaydina bagli degil. Hesabi bir otorite "
            "kaydina baglamadan 'benim kitaplarim' cevaplanamaz."
        )

    return user.subject_entity_id


def publisher_titles(executor, user, *, limit: int = 200) -> list[Mapping]:
    """This publisher's titles, most widely held first."""

    return executor.execute(
        text(TITLES),
        {"agent_id": _agent(user), "limit": limit},
    ).mappings().all()


def library_report(executor, user, work_id) -> list[Mapping]:
    """Which libraries hold one title, and which printing of it."""

    return executor.execute(
        text(HOLDERS),
        {"agent_id": _agent(user), "work_id": work_id},
    ).mappings().all()


def summary(executor, user) -> Mapping:
    """The numbers a publisher wants on arrival."""

    return executor.execute(
        text(SUMMARY),
        {"agent_id": _agent(user)},
    ).mappings().one()
