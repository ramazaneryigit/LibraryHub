"""Generate scale fixtures across all three planes, and purge them again.

Why
---
The development database holds a dozen items and fewer than twenty works, which
is too small for a whole class of defects to show up: row level security across
many tenants, index behaviour once a table stops fitting in a single page,
pagination, and the deliberately expensive code paths (the 20-branch OR in
`/search`, the trigram blocking in reconciliation).

This creates volume in all three planes and injects the awkward cases on
purpose, so the checks in `run_scale_checks.py` have something to fail on.

What it creates
---------------
* Control Plane: N tenants, each with an organization, an authority
  `collective_agents` record, a default branch and a `tenant_databases` row.
* Tenant Data Plane: holdings and items spread over those tenants. The same
  Manifestation is deliberately held by many different institutions -- that is
  the whole point of the Global/Tenant split, and it needs to be exercised.
* Global Knowledge Plane: extra works with titles in several scripts.

Deliberate edge cases
---------------------
* tenants with no items at all, and one tenant with a disproportionate share;
* items with no barcode;
* the *same* barcode in different tenants (allowed: barcode uniqueness is
  tenant-wide by OD3, not global);
* over-long barcodes, Cyrillic and Arabic shelfmarks;
* Holdings that target an Expression instead of a Manifestation;
* electronic Holdings with no Items at all;
* titles that normalize to nothing (punctuation only) and very long titles.

Everything it writes is tagged: tenants use a `scale-` slug prefix and
descriptions carry ``[scale-fixture]``. `--purge` removes exactly that set and
nothing else.

It connects as the schema owner (`DATABASE_URL`). It must: it writes across
tenants and across planes, and row level security would (correctly) refuse both
for the application role.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python generate_scale_fixtures.py"
    docker compose exec -T api sh -c "cd /app/scripts && python generate_scale_fixtures.py --purge"
"""

import argparse
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.core.ids import uuid7
from app.core.text import normalize_text


MARKER = "[scale-fixture]"
SLUG_PREFIX = "scale-"


# Titles chosen to exercise normalization and encoding: Latin with diacritics,
# Cyrillic, Arabic, an over-long one and one that has no comparable content.
TITLE_SHAPES = [
    "Ölçek Kaydı {n}",
    "Масштабная запись {n}",
    "سجل المقياس {n}",
    "Scale Record {n}",
    "...",
]


def _titles(rng: random.Random, count: int) -> list[str]:
    titles = []
    for index in range(count):
        shape = TITLE_SHAPES[index % len(TITLE_SHAPES)]
        title = shape.format(n=index)
        if index % 50 == 0:
            title = title + " " + ("çok uzun başlık " * 60)
        titles.append(title)
    return titles


def purge(connection) -> None:
    """Remove every scale fixture, and nothing else.

    Both subtype tables carry ``ON DELETE CASCADE`` from ``public.entities``, so
    the global-plane rows are removed by deleting the entity rather than the
    subtype: that guarantees the registry does not keep orphans behind.
    """

    tenant_ids = [
        row[0]
        for row in connection.execute(
            text("select id from control.tenants where slug like :p"),
            {"p": f"{SLUG_PREFIX}%"},
        ).fetchall()
    ]

    if tenant_ids:
        # Children before parents.
        for statement in (
            "delete from tenant.items where tenant_id = any(:ids)",
            "delete from tenant.holdings where tenant_id = any(:ids)",
            "delete from control.tenant_databases where tenant_id = any(:ids)",
            "delete from control.branches where tenant_id = any(:ids)",
            "delete from control.organizations where tenant_id = any(:ids)",
        ):
            connection.execute(text(statement), {"ids": tenant_ids})

        connection.execute(
            text("delete from control.tenants where id = any(:ids)"),
            {"ids": tenant_ids},
        )

    # Global plane: drop the entities whose subtype row carries the marker.
    #
    # Expressions and Manifestations are here because the fixtures create their
    # own now -- see the block above. Without them a purge would leave the
    # bibliographic records behind and the next run would attach to nothing.
    removed = connection.execute(
        text(
            """
            delete from public.entities e
            where (
                    e.entity_type in ('WORK', 'ORGANIZATION')
                and (
                        exists (
                            select 1 from public.works w
                            where w.entity_id = e.id and w.description like :m
                        )
                     or exists (
                            select 1 from public.collective_agents ca
                            where ca.entity_id = e.id and ca.description like :m
                        )
                    )
                  )
               or (
                    e.entity_type = 'EXPRESSION'
                and exists (
                        select 1 from public.expressions x
                        where x.entity_id = e.id and x.description like :m
                    )
                  )
               or (
                    e.entity_type = 'MANIFESTATION'
                and exists (
                        select 1 from public.manifestations mf
                        where mf.entity_id = e.id and mf.notes like :m
                    )
                  )
            """
        ),
        {"m": f"%{MARKER}%"},
    ).rowcount

    print(f"silinen tenant          : {len(tenant_ids)}")
    print(f"silinen global entity   : {removed}")
    print("temizlik tamam.")


def generate(connection, organizations: int, works: int, items: int, seed: int) -> None:
    rng = random.Random(seed)

    # ------------------------------------------------------------ authority
    authority_rows = []
    for index in range(1, organizations + 1):
        entity_id = uuid7()
        authority_rows.append(
            {"id": entity_id, "name": f"Scale Fixture Organization {index}"}
        )

    connection.execute(
        text(
            """
            insert into public.entities (id, entity_type, created_at, updated_at)
            values (:id, 'ORGANIZATION', now(), now())
            """
        ),
        [{"id": row["id"]} for row in authority_rows],
    )
    connection.execute(
        text(
            """
            insert into public.collective_agents
                (entity_id, canonical_name, agent_type, description)
            values (:id, :name, 'organization', :marker)
            """
        ),
        [
            {"id": row["id"], "name": row["name"], "marker": MARKER}
            for row in authority_rows
        ],
    )

    # -------------------------------------------------------- control plane
    tenants = []
    for index in range(1, organizations + 1):
        tenants.append(
            {
                "id": uuid7(),
                "slug": f"{SLUG_PREFIX}{index:04d}",
                "name": f"Scale Fixture Organization {index}",
                "organization_id": uuid7(),
                "branch_id": uuid7(),
                "authority_id": authority_rows[index - 1]["id"],
            }
        )

    connection.execute(
        text(
            """
            insert into control.tenants
                (id, slug, display_name, status, cluster_id, created_at, updated_at)
            values (:id, :slug, :name, 'active', 'primary', now(), now())
            """
        ),
        tenants,
    )
    connection.execute(
        text(
            """
            insert into control.organizations
                (id, tenant_id, collective_agent_entity_id, name, org_type, created_at)
            values (:organization_id, :id, :authority_id, :name, 'university', now())
            """
        ),
        tenants,
    )
    connection.execute(
        text(
            """
            insert into control.branches
                (id, tenant_id, organization_id, code, name, is_default, created_at)
            values (:branch_id, :id, :organization_id, 'MAIN', 'Main', true, now())
            """
        ),
        tenants,
    )
    connection.execute(
        text(
            """
            insert into control.tenant_databases
                (tenant_id, cluster_id, dsn_secret_ref, updated_at)
            values (:id, 'primary', 'env:DATABASE_URL', now())
            """
        ),
        tenants,
    )

    # ---------------------------------------------------- global plane works
    work_rows = []

    if works:
        titles = _titles(rng, works)
        work_rows = []
        for title in titles:
            entity_id = uuid7()
            work_rows.append(
                {
                    "id": entity_id,
                    "title": title,
                    "normalized": normalize_text(title),
                    "marker": MARKER,
                }
            )

        connection.execute(
            text(
                """
                insert into public.entities (id, entity_type, created_at, updated_at)
                values (:id, 'WORK', now(), now())
                """
            ),
            [{"id": row["id"]} for row in work_rows],
        )
        connection.execute(
            text(
                """
                insert into public.works
                    (entity_id, canonical_title, normalized_title, original_language,
                     work_type, description, created_at)
                values (:id, :title, :normalized, 'tr', 'textbook', :marker, now())
                """
            ),
            work_rows,
        )

    # --------------------------- global plane: expressions and manifestations
    #
    # This block replaced a query. The fixtures used to link their holdings to the
    # first twelve manifestations ordered by id, under a comment about one
    # bibliographic record being held by many institutions. The intent was right;
    # the choice of record was not. Those were *real* records, so 930 fixture
    # holdings landed on genuine works and buried the libraries that actually hold
    # them -- the 1867 Russian edition of a novel came out with ninety-two
    # institutions attached to it.
    #
    # A fixture may only ever point at a record it created itself. That is the
    # rule this block exists to make true, and `run_scale_checks.py` asserts it.
    expression_ids = []
    manifestation_ids = []
    new_entity_rows = []
    expression_rows = []
    manifestation_rows = []
    work_expression_rows = []
    expression_manifestation_rows = []

    for index, work in enumerate(work_rows, start=1):
        expression_id = uuid7()
        manifestation_id = uuid7()

        expression_ids.append(expression_id)
        manifestation_ids.append(manifestation_id)

        new_entity_rows.append({"id": expression_id, "type": "EXPRESSION"})
        new_entity_rows.append({"id": manifestation_id, "type": "MANIFESTATION"})

        expression_rows.append(
            {
                "id": expression_id,
                "language": "tr",
                "form": "written",
                "description": f"{MARKER} ifade {index}",
            }
        )
        manifestation_rows.append(
            {
                "id": manifestation_id,
                "statement": f"{MARKER} Yayincilik",
                "date": str(2000 + index % 25),
                "edition": f"{1 + index % 5}. baski",
                "carrier": "kitap",
                "extent": f"{100 + index} sayfa",
                "notes": MARKER,
            }
        )
        work_expression_rows.append(
            {"work_id": work["id"], "expression_id": expression_id}
        )
        expression_manifestation_rows.append(
            {
                "expression_id": expression_id,
                "manifestation_id": manifestation_id,
            }
        )

    if new_entity_rows:
        connection.execute(
            text(
                "insert into public.entities "
                "(id, entity_type, created_at, updated_at) "
                "values (:id, :type, now(), now())"
            ),
            new_entity_rows,
        )
        connection.execute(
            text(
                "insert into public.expressions "
                "(entity_id, language, expression_form, description) "
                "values (:id, :language, :form, :description)"
            ),
            expression_rows,
        )
        connection.execute(
            text(
                "insert into public.manifestations "
                "(entity_id, publication_statement, publication_date, "
                " edition_statement, carrier_type, extent, notes) "
                "values (:id, :statement, :date, :edition, :carrier, "
                "        :extent, :notes)"
            ),
            manifestation_rows,
        )
        connection.execute(
            text(
                "insert into public.work_expression "
                "(work_entity_id, expression_entity_id) "
                "values (:work_id, :expression_id)"
            ),
            work_expression_rows,
        )
        connection.execute(
            text(
                "insert into public.expression_manifestation "
                "(expression_entity_id, manifestation_entity_id) "
                "values (:expression_id, :manifestation_id)"
            ),
            expression_manifestation_rows,
        )

    # ------------------------------------------------------ tenant plane rows
    if not manifestation_ids:
        print("UYARI: hic manifestation yok, tenant plane'i bos birakildi.")
        return

    holding_rows = []
    item_rows = []

    # Tenants with no items at all, plus one carrying a disproportionate share.
    skip_every = 10
    skew_index = 2

    for position, tenant in enumerate(tenants, start=1):
        per_tenant = items // organizations
        if position == skew_index:
            per_tenant *= 4
        elif position % skip_every == 0:
            per_tenant = 0

        if per_tenant <= 0:
            continue

        for slot in range(per_tenant):
            manifestation_id = manifestation_ids[slot % len(manifestation_ids)]
            holding_id = uuid7()

            # Some Holdings describe an Expression rather than a Manifestation.
            if slot % 11 == 0 and expression_ids:
                target_manifestation = None
                target_expression = expression_ids[slot % len(expression_ids)]
            else:
                target_manifestation = manifestation_id
                target_expression = None

            holding_type = "electronic" if slot % 13 == 0 else "physical"

            holding_rows.append(
                {
                    "id": holding_id,
                    "tenant_id": tenant["id"],
                    "branch_id": tenant["branch_id"],
                    "manifestation_id": target_manifestation,
                    "expression_id": target_expression,
                    "holding_type": holding_type,
                    "key": f"scale-{position:04d}-{slot:03d}",
                    "call_number": f"ÖLÇ {position}/{slot}",
                }
            )

            # Electronic Holdings deliberately have no Items at all.
            if holding_type == "electronic":
                continue

            barcode = f"SCALE-{position:04d}-{slot:04d}"

            if slot % 10 == 3:
                barcode = None                      # uncatalogued copy
            elif slot % 25 == 7:
                # The SAME value in several tenants -- allowed, because barcode
                # uniqueness is tenant-wide (OD3). It must still be unique
                # within a tenant, which is why the value is keyed on the slot
                # and not on slot % n: collapsing several slots onto one value
                # trips uq_items_tenant_barcode, which is the constraint doing
                # its job.
                barcode = f"SHARED-{slot:03d}"
            elif slot % 40 == 11:
                barcode = ("U" * 170) + f"{slot:04d}"  # over-long, unique per tenant
            elif slot % 30 == 5:
                barcode = f"МСК-{position}-{slot}"  # Cyrillic barcode

            item_rows.append(
                {
                    "id": uuid7(),
                    "tenant_id": tenant["id"],
                    "holding_id": holding_id,
                    "barcode": barcode,
                    "shelfmark": f"МОСКВА {position} {slot}" if slot % 17 == 0 else f"RAF-{slot}",
                    "availability": rng.choice(["available", "on_loan", "reference"]),
                }
            )

    if holding_rows:
        connection.execute(
            text(
                """
                insert into tenant.holdings
                    (id, tenant_id, branch_id, manifestation_entity_id,
                     expression_entity_id, holding_type, call_number,
                     local_holding_key, status, created_at, updated_at)
                values
                    (:id, :tenant_id, :branch_id, :manifestation_id, :expression_id,
                     :holding_type, :call_number, :key, 'active', now(), now())
                """
            ),
            holding_rows,
        )

    if item_rows:
        connection.execute(
            text(
                """
                insert into tenant.items
                    (id, tenant_id, holding_id, barcode, shelfmark,
                     availability_status, lifecycle_status, created_at, updated_at)
                values
                    (:id, :tenant_id, :holding_id, :barcode, :shelfmark,
                     :availability, 'active', now(), now())
                """
            ),
            item_rows,
        )

    print(f"  tenant/organization : {len(tenants)}")
    print(f"  work (global plane) : {works}")
    print(f"  holding             : {len(holding_rows)}")
    print(f"  item                : {len(item_rows)}")
    print(f"  bunlardan barkodsuz : {sum(1 for r in item_rows if r['barcode'] is None)}")
    print(f"  elektronik holding  : {sum(1 for r in holding_rows if r['holding_type'] == 'electronic')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organizations", type=int, default=100)
    parser.add_argument("--works", type=int, default=300)
    parser.add_argument("--items", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="remove every scale fixture instead of creating them",
    )
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.purge:
            purge(connection)
            return 0

        print(
            f"Ölçek verisi üretiliyor: {args.organizations} organizasyon, "
            f"{args.works} work, {args.items} item (seed={args.seed})"
        )
        generate(
            connection,
            organizations=args.organizations,
            works=args.works,
            items=args.items,
            seed=args.seed,
        )
        print("\nTamamlandı. Silmek için: --purge")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
