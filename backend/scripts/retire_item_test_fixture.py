"""Retire the ITEM portion of the `controlled_test` fixture.

Why anything has to be retired
------------------------------
`entities.entity_type` cannot lose the value `'ITEM'` while a surviving record
still names an entity of that type, and Aşama 6 removes it. `entity_merges` holds
one such record, part of a deliberate canonical-redirect fixture that covers
eight entity types.

Why only the ITEM part
----------------------
The fixture is not junk. It demonstrates that canonical redirects work for every
kind of entity, and seven eighths of it stays useful. It is only the item instance
that stops meaning anything: an item is no longer a global entity, so it cannot
take part in the global identity registry at all. Its old identity is preserved by
`tenant.items.legacy_entity_id`, which is what the compatibility view hands back
to a client that still holds the legacy id -- a mapping, not a redirect.

The items themselves are untouched. They migrated correctly and remain the
tenant's copies; only the global-identity record about them goes.

Usage
-----
    ... python retire_item_test_fixture.py           # report only
    ... python retire_item_test_fixture.py --apply   # remove

See docs/architecture-v2.md §0.15 and §0.16.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text


MERGES_TO_RETIRE = """
select em.id, em.source_entity_id, em.target_entity_id, em.reason
from entity_merges em
where exists (
    select 1 from entities e
    where e.entity_type = 'ITEM'
      and e.id in (em.source_entity_id, em.target_entity_id)
)
"""

RELATIONS_TO_RETIRE = """
select iar.item_entity_id, iar.agent_entity_id, iar.role
from item_agent_relation iar
where iar.role = 'controlled_test_holder'
  and exists (
      select 1 from entities e
      where e.entity_type = 'ITEM' and e.id = iar.item_entity_id
  )
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually remove the records; without it nothing is changed",
    )
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        merges = connection.execute(text(MERGES_TO_RETIRE)).fetchall()
        relations = connection.execute(text(RELATIONS_TO_RETIRE)).fetchall()

        print("ITEM entity'sine bakan kayitlar\n")

        print(f"  entity_merges        : {len(merges)}")
        for merge_id, source, target, reason in merges:
            print(f"    {merge_id}")
            print(f"      kaynak {source}")
            print(f"      hedef  {target}")
            print(f"      sebep  {reason}")

        print(f"  item_agent_relation  : {len(relations)}")
        for item_id, agent_id, role in relations:
            print(f"    {item_id} - {role}")

        if not merges and not relations:
            print("\nEmekliye ayrilacak kayit yok; Asama 6 yolu acik.")
            return 0

        # Everything else in the fixture stays, and saying so here is the point:
        # a later reader should not have to guess whether the whole fixture went.
        others = connection.execute(
            text(
                """
                select es.entity_type, count(*)
                from entity_merges em
                join entities es on es.id = em.source_entity_id
                where em.merge_method = 'controlled_test'
                  and es.entity_type <> 'ITEM'
                group by 1
                order by 1
                """
            )
        ).fetchall()

        if others:
            print("\n  korunacak diger tipler (fixture'in geri kalani):")
            for entity_type, count in others:
                print(f"    {entity_type:16} {count}")

        if not args.apply:
            print("\nDENEME MODU. Uygulamak icin --apply ekleyin.")
            return 0

        connection.execute(
            text(
                "delete from entity_merges where id = any(:ids)"
            ),
            {"ids": [row[0] for row in merges]},
        )

        connection.execute(
            text(
                """
                delete from item_agent_relation
                where role = 'controlled_test_holder'
                  and item_entity_id = any(:ids)
                """
            ),
            {"ids": [row[0] for row in relations]},
        )

        print(
            f"\nUygulandi: {len(merges)} birlesme ve "
            f"{len(relations)} iliski emekliye ayrildi."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
