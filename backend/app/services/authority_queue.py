"""The authority queue: where a resemblance goes when it is not proof.

`authority.suggest` decides nothing on weak evidence, and that rule only works if
the resemblance has somewhere to go. Otherwise the choice is between merging
wrongly and ignoring the match, and ignoring it is how a catalogue accumulates the
forty-people problem while nobody is looking.

So this records rather than acts. Nothing in the catalogue changes; a row appears
saying these two look alike and why, and a person decides.

Merging is the one operation here that changes anything, and it is deliberately
small: point the incoming relation at the existing entity. The work the *other*
record did is left alone -- `entity_merges` already exists for that, and a second
implementation of merging would eventually disagree with the first about what
happened.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy import text

from ..core.ids import uuid7

__all__ = [
    "decide",
    "enqueue",
    "find_existing",
    "list_queue",
    "resolve_agent",
]


def find_existing(executor, name: str, limit: int = 200) -> list[Mapping]:
    """People and organizations the catalogue already has, for `suggest` to sort.

    Reads both tables into one list because `suggest` does not care which a name
    belongs to -- a publisher and a person are matched the same way, and returning
    them separately would push that decision back to every caller.
    """

    rows = executor.execute(
        text(
            "select p.entity_id, p.canonical_name as name, "
            "       (select i.value from public.identifiers i "
            "         where i.entity_id = p.entity_id and i.scheme = 'ORCID' "
            "         limit 1) as orcid, "
            "       null::text as dates "
            "from public.persons p "
            "union all "
            "select ca.entity_id, ca.canonical_name, null, null "
            "from public.collective_agents ca "
            "limit :limit"
        ),
        {"limit": limit},
    ).mappings().all()

    return [
        {
            "entity_id": str(row["entity_id"]),
            "name": row["name"],
            "orcid": row["orcid"],
            "dates": row["dates"],
        }
        for row in rows
    ]


def enqueue(
    executor,
    *,
    entity_type: str,
    incoming_name: str,
    candidates,
    source_system_id=None,
) -> int:
    """Record the weak candidates. Returns how many were newly queued.

    The `on conflict do nothing` is on the partial unique index, so a second run
    of the same import adds nothing and the count stays honest.
    """

    queued = 0

    for candidate in candidates:
        if candidate.decides or candidate.entity_id is None:
            continue

        result = executor.execute(
            text(
                "insert into public.authority_candidates "
                "(id, entity_type, incoming_name, candidate_entity_id, "
                " candidate_name, score, strength, reason, source_system_id, "
                " status, created_at) "
                "values (:id, :entity_type, :incoming_name, :candidate_id, "
                "        :candidate_name, :score, :strength, :reason, "
                "        :source_system_id, 'open', now()) "
                "on conflict do nothing"
            ),
            {
                "id": uuid7(),
                "entity_type": entity_type,
                "incoming_name": incoming_name,
                "candidate_id": candidate.entity_id,
                "candidate_name": candidate.name,
                "score": candidate.score,
                "strength": candidate.strength,
                "reason": candidate.reason,
                "source_system_id": source_system_id,
            },
        )

        queued += result.rowcount or 0

    return queued


def list_queue(executor, *, status: str = "open", limit: int = 100) -> list[Mapping]:
    """The queue, best matches first.

    Ordered by score because the first rows are the ones worth looking at: a
    reviewer working down the list should meet the plausible pairs before the
    merely similar ones.
    """

    return executor.execute(
        text(
            "select a.id, a.entity_type, a.incoming_name, a.candidate_name, "
            "       a.candidate_entity_id, a.score, a.reason, a.status, "
            "       a.created_at, "
            "       s.name as source_name "
            "from public.authority_candidates a "
            "left join public.source_systems s on s.id = a.source_system_id "
            "where a.status = :status "
            "order by a.score desc, a.created_at "
            "limit :limit"
        ),
        {"status": status, "limit": limit},
    ).mappings().all()


def decide(
    executor,
    candidate_id,
    *,
    status: str,
    reviewed_by=None,
    note: str | None = None,
) -> None:
    """Record what a person decided. Does not merge anything by itself."""

    if status not in ("merged", "kept_separate", "dismissed"):
        raise ValueError("a decision is 'merged', 'kept_separate' or 'dismissed'")

    executor.execute(
        text(
            "update public.authority_candidates "
            "set status = :status, reviewed_by = :reviewed_by, "
            "    reviewed_at = now(), review_note = :note "
            "where id = :id and status = 'open'"
        ),
        {
            "id": candidate_id,
            "status": status,
            "reviewed_by": reviewed_by,
            "note": note,
        },
    )


def resolve_agent(
    executor,
    name: str,
    agent_type: str,
    *,
    source_system_id=None,
    queue: bool = True,
) -> tuple[Any, bool]:
    """The authority record for this name, creating one only if nothing decides.

    Returns the id and whether anything was queued for a person to look at. The
    caller gets both because "used an existing record" and "created one and asked
    about two others" are different outcomes and the import report should say
    which happened.
    """

    from ..core.authority import suggest

    existing = find_existing(executor, name)
    candidates = suggest(name, existing)

    deciding = [candidate for candidate in candidates if candidate.decides]

    if deciding:
        best = deciding[0]

        if queue:
            enqueue(
                executor,
                entity_type="PERSON" if agent_type != "publisher" else "ORGANIZATION",
                incoming_name=name,
                candidates=[c for c in candidates if not c.decides],
                source_system_id=source_system_id,
            )

        return uuid.UUID(best.entity_id), False

    # Nothing decides, so a record is created and the resemblances are recorded
    # for a person rather than acted on. This is the whole point: a new spelling
    # makes a new person, and the catalogue is told that two people may be one.
    queued = 0

    if queue:
        queued = enqueue(
            executor,
            entity_type="PERSON" if agent_type != "publisher" else "ORGANIZATION",
            incoming_name=name,
            candidates=candidates,
            source_system_id=source_system_id,
        )

    return None, bool(queued)
