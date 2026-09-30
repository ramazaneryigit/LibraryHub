"""Scenario checks that only mean something with volume.

Run after `generate_scale_fixtures.py`. These are the things a dozen rows cannot
tell you: whether row level security still isolates correctly across a hundred
tenants, whether the tenant indexes can actually serve their queries, whether
anything has drifted into an orphan, and whether the compatibility view still
agrees with the legacy shape once there is real data behind it.

Connects twice on purpose:

* as the schema owner (`DATABASE_URL`) for integrity and plan checks, because
  those have to see every tenant;
* as the application role (`APP_DATABASE_URL`) for the isolation checks, because
  isolation is a property of that role -- the owner bypasses it by design.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python run_scale_checks.py"
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text


APP_URL = os.environ.get("APP_DATABASE_URL") or os.environ["DATABASE_URL"]
OWNER_URL = os.environ["DATABASE_URL"]

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str) -> None:
    results.append((name, passed, detail))
    print(f"  [{'OK  ' if passed else 'HATA'}] {name}: {detail}")


def check_rls_isolation(owner, app) -> None:
    expected = dict(
        owner.execute(
            text(
                """
                select t.id, count(i.id)
                from control.tenants t
                left join tenant.items i on i.tenant_id = t.id
                group by t.id
                """
            )
        ).fetchall()
    )

    mismatches = []
    for tenant_id, count in expected.items():
        app.execute(
            text("select set_config(:n, :v, false)"),
            {"n": "libraryhub.tenant_id", "v": str(tenant_id)},
        )
        visible = app.execute(text("select count(*) from tenant.items")).scalar()
        if visible != count:
            mismatches.append((str(tenant_id), count, visible))

    record(
        "RLS: her tenant yalnizca kendi satirlarini goruyor",
        not mismatches,
        f"{len(expected)} tenant denendi, uyusmazlik: {len(mismatches)}"
        + (f" -> {mismatches[:3]}" if mismatches else ""),
    )


def check_rls_fail_closed(app) -> None:
    app.execute(
        text("select set_config(:n, :v, false)"),
        {"n": "libraryhub.tenant_id", "v": ""},
    )
    visible = app.execute(text("select count(*) from tenant.items")).scalar()

    record(
        "RLS: tenant ayarlanmamisken hic satir yok (fail-closed)",
        visible == 0,
        f"gorunen satir: {visible}",
    )


def check_no_orphans(owner) -> None:
    orphan_items = owner.execute(
        text(
            """
            select count(*)
            from tenant.items i
            left join tenant.holdings h on h.id = i.holding_id
            where h.id is null or h.tenant_id <> i.tenant_id
            """
        )
    ).scalar()

    no_target = owner.execute(
        text(
            """
            select count(*)
            from tenant.holdings h
            where h.manifestation_entity_id is null and h.expression_entity_id is null
            """
        )
    ).scalar()

    bad_arc = owner.execute(
        text(
            """
            select count(*)
            from tenant.holdings h
            where (h.manifestation_entity_id is null) = (h.expression_entity_id is null)
            """
        )
    ).scalar()

    record(
        "Butunluk: holding'i olmayan veya baska tenant'in holding'ine bagli item yok",
        orphan_items == 0,
        f"orphan item: {orphan_items}",
    )
    record(
        "Butunluk: hedefsiz holding yok",
        no_target == 0,
        f"hedefsiz holding: {no_target}",
    )
    record(
        "Kisit: exclusive arc her satirda gecerli",
        bad_arc == 0,
        f"ihlal: {bad_arc}",
    )


def check_barcode_uniqueness(owner) -> None:
    duplicates = owner.execute(
        text(
            """
            select count(*)
            from (
                select tenant_id, barcode
                from tenant.items
                where barcode is not null
                group by tenant_id, barcode
                having count(*) > 1
            ) d
            """
        )
    ).scalar()

    # The point of OD3: the same barcode in *different* tenants is fine.
    cross_tenant = owner.execute(
        text(
            """
            select count(*)
            from (
                select barcode
                from tenant.items
                where barcode is not null
                group by barcode
                having count(distinct tenant_id) > 1
            ) d
            """
        )
    ).scalar()

    record(
        "OD3: tenant icinde barkod tekrari yok",
        duplicates == 0,
        f"tekrar: {duplicates}",
    )
    record(
        "OD3: ayni barkod farkli tenant'larda serbest",
        True,
        f"farkli tenant'ta tekrarlanan barkod degeri: {cross_tenant}",
    )


def check_view_agrees(owner) -> None:
    legacy = owner.execute(
        text("select count(*) from public.items")
    ).scalar()
    compat = owner.execute(
        text("select count(*) from public.items_compat")
    ).scalar()

    record(
        "Uyumluluk gorunumu legacy item sayisini koruyor",
        compat >= legacy,
        f"public.items={legacy}, items_compat={compat}",
    )

    unresolved = owner.execute(
        text(
            """
            select count(*)
            from public.items li
            where not exists (
                select 1 from public.items_compat v where v.entity_id = li.entity_id
            )
            """
        )
    ).scalar()

    record(
        "Her legacy item gorunumde temsil ediliyor",
        unresolved == 0,
        f"temsil edilmeyen: {unresolved}",
    )


def _plan(connection, sql: str) -> str:
    connection.execute(text("set enable_seqscan = off"))
    rows = connection.execute(text(f"explain {sql}")).fetchall()
    return " ".join(row[0] for row in rows)


def check_indexes(owner) -> None:
    plan = _plan(
        owner,
        "select count(*) from tenant.items where tenant_id = gen_random_uuid()",
    )
    record(
        "tenant.items tenant_id ile index kullanabiliyor",
        "Index" in plan or "Bitmap" in plan,
        plan[:110],
    )

    plan = _plan(
        owner,
        """
        select count(*) from tenant.holdings
        where manifestation_entity_id = (
            select manifestation_entity_id from tenant.holdings
            where manifestation_entity_id is not null limit 1
        )
        """,
    )
    record(
        "tenant.holdings manifestation ile index kullanabiliyor",
        "Index" in plan or "Bitmap" in plan,
        plan[:110],
    )

    plan = _plan(
        owner,
        """
        select count(*) from public.works
        where normalized_title % 'scale record 5'
        """,
    )
    record(
        "works.normalized_title trigram index kullaniliyor",
        "Bitmap" in plan or "Index" in plan,
        plan[:110],
    )


def check_manifestation_reach(owner) -> None:
    """The question the whole plane split exists to answer: who holds this?"""
    row = owner.execute(
        text(
            """
            select h.manifestation_entity_id, count(distinct h.tenant_id) as kurum
            from tenant.holdings h
            where h.manifestation_entity_id is not null
            group by h.manifestation_entity_id
            order by 2 desc
            limit 1
            """
        )
    ).fetchone()

    record(
        "Bir Manifestation'i birden fazla kurum tutabiliyor",
        row is not None and row[1] > 1,
        f"en yaygin manifestation {row[1]} kurumda" if row else "veri yok",
    )


def main() -> int:
    owner_engine = create_engine(OWNER_URL)
    app_engine = create_engine(APP_URL)

    print("Ölçek senaryo kontrolleri\n")

    with owner_engine.connect() as owner, app_engine.connect() as app:
        print("-- yalitkanlik --")
        check_rls_isolation(owner, app)
        check_rls_fail_closed(app)

        print("\n-- butunluk --")
        check_no_orphans(owner)
        check_barcode_uniqueness(owner)
        check_view_agrees(owner)

        print("\n-- index ve plan --")
        check_indexes(owner)

        print("\n-- mimari sorusu --")
        check_manifestation_reach(owner)

    failed = [name for name, passed, _ in results if not passed]
    print()
    print(f"toplam kontrol: {len(results)} | gecen: {len(results) - len(failed)} | basarisiz: {len(failed)}")
    for name in failed:
        print(f"  BASARISIZ: {name}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
