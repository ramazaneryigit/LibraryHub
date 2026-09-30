"""Give the unassigned migrated items their institution.

Why this is a script and not a migration
----------------------------------------
Migration `c5d8f1b69a07` attributes an item only through
`item_agent_relation.role = 'holding_institution'` -- the rule the API itself
used -- and puts everything else in the `unassigned` tenant instead of guessing
from the barcode. That was deliberate: guessing silently is worse than leaving a
row visibly unattributed.

Closing that queue is a *curation* decision about specific known records, not a
schema evolution. Baking barcode prefixes into a migration would make it run
that inference on every environment, including ones with different data. So the
decision lives here, as an explicit reviewed mapping, with a dry run.

Why it connects as the schema owner
-----------------------------------
Row level security makes cross-tenant moves impossible for the application role
on purpose, and that is worth stating because it looks like a bug the first
time:

* with `libraryhub.tenant_id` set to the *source* tenant, the policy's USING
  clause matches the old row but its WITH CHECK rejects the new `tenant_id`;
* with it set to the *target* tenant, USING does not match the old row, so the
  row is not even visible and nothing is updated.

Moving a row between tenants is therefore an administrative operation and runs
with `DATABASE_URL` (the owner), not `APP_DATABASE_URL`.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python assign_unassigned_items.py"
    docker compose exec -T api sh -c "cd /app/scripts && python assign_unassigned_items.py --apply"

Without `--apply` nothing is written.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text


# Reviewed mapping: barcode -> organization name. Names rather than slugs
# because the decision is about institutions, not about generated keys.
ASSIGNMENTS = {
    "KKU-AKADEMIK-0001": "Kırıkkale Üniversitesi",
    "KKU-ANSIKLOPEDI-SET-0001": "Kırıkkale Üniversitesi",
    "KKU-COCUK-0001": "Kırıkkale Üniversitesi",
    "KKU-SOZLUK-0001": "Kırıkkale Üniversitesi",
    "KKU-TEZ-0001": "Kırıkkale Üniversitesi",
    "TEST-CANONICAL-ITEM-001": "Canonical Redirect Test Organization B",
    "TEST-ITEM-REDIRECT-SOURCE": "Canonical Redirect Test Organization B",
}

FALLBACK_SLUG = "unassigned"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the changes; without it the script only reports",
    )
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        pending = connection.execute(
            text(
                """
                select i.barcode, i.entity_id
                from tenant.items ti
                join control.tenants t on t.id = ti.tenant_id
                join public.items i on i.entity_id = ti.legacy_entity_id
                where t.slug = :slug
                order by i.barcode
                """
            ),
            {"slug": FALLBACK_SLUG},
        ).fetchall()

        print(f"'{FALLBACK_SLUG}' tenant'inda {len(pending)} nüsha var.\n")

        moved = 0
        unmatched = []

        for barcode, entity_id in pending:
            organization = ASSIGNMENTS.get(barcode)

            if organization is None:
                unmatched.append(barcode)
                continue

            target = connection.execute(
                text(
                    """
                    select t.id as tenant_id, b.id as branch_id
                    from control.organizations o
                    join control.tenants t on t.id = o.tenant_id
                    join control.branches b on b.organization_id = o.id
                    where o.name = :name
                    order by b.is_default desc, b.code
                    limit 1
                    """
                ),
                {"name": organization},
            ).fetchone()

            if target is None:
                print(f"  {barcode:26} HEDEF YOK: '{organization}' bulunamadi")
                unmatched.append(barcode)
                continue

            manifestation_id = connection.execute(
                text(
                    """
                    select mi.manifestation_entity_id
                    from public.manifestation_item mi
                    where mi.item_entity_id = :item
                    """
                ),
                {"item": entity_id},
            ).scalar()

            if manifestation_id is None:
                print(f"  {barcode:26} manifestation bagi yok, atlandi")
                unmatched.append(barcode)
                continue

            if not args.apply:
                print(f"  {barcode:26} -> {organization} (deneme)")
                moved += 1
                continue

            # Reuse the holding if the target tenant already has one for this
            # manifestation, otherwise create it with the same key convention
            # the migration used.
            holding_id = connection.execute(
                text(
                    """
                    select h.id
                    from tenant.holdings h
                    where h.tenant_id = :tenant_id
                      and h.branch_id = :branch_id
                      and h.manifestation_entity_id = :manifestation_id
                    limit 1
                    """
                ),
                {
                    "tenant_id": target.tenant_id,
                    "branch_id": target.branch_id,
                    "manifestation_id": manifestation_id,
                },
            ).scalar()

            if holding_id is None:
                holding_id = connection.execute(
                    text(
                        """
                        insert into tenant.holdings
                            (id, tenant_id, branch_id, manifestation_entity_id,
                             holding_type, local_holding_key, status,
                             created_at, updated_at)
                        values
                            (gen_random_uuid(), :tenant_id, :branch_id,
                             :manifestation_id, 'physical',
                             'migrated-' || replace(cast(:manifestation_id as text), '-', ''),
                             'active', now(), now())
                        returning id
                        """
                    ),
                    {
                        "tenant_id": target.tenant_id,
                        "branch_id": target.branch_id,
                        "manifestation_id": manifestation_id,
                    },
                ).scalar()

            connection.execute(
                text(
                    """
                    update tenant.items
                    set tenant_id = :tenant_id, holding_id = :holding_id
                    where legacy_entity_id = :item
                    """
                ),
                {
                    "tenant_id": target.tenant_id,
                    "holding_id": holding_id,
                    "item": entity_id,
                },
            )

            print(f"  {barcode:26} -> {organization}")
            moved += 1

        print()
        print(f"atanan: {moved}")
        print(f"atanmamis kalan: {len(unmatched)}")
        for barcode in unmatched:
            print(f"  {barcode}")

        if not args.apply:
            print("\nDENEME modu: hicbir sey yazilmadi. Uygulamak icin --apply.")

        # Leaving the fallback tenant empty is not an error -- it stays in place
        # so a future unattributable item still has somewhere honest to land.
        remaining = connection.execute(
            text(
                """
                select count(*)
                from tenant.items ti
                join control.tenants t on t.id = ti.tenant_id
                where t.slug = :slug
                """
            ),
            {"slug": FALLBACK_SLUG},
        ).scalar()

        print(f"'{FALLBACK_SLUG}' tenant'inda kalan nüsha: {remaining}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
