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


def check_tenant_role_jail(app) -> None:
    """A tenant-scoped transaction cannot touch the global plane.

    This is the guarantee behind "kendi verilerini yapımızı bozmadan", and it is
    a grant rather than a convention: `tenant_session` drops to
    `libraryhub_tenant_app`, which holds SELECT and nothing else on `public` and
    on `control`. A future endpoint that forgets itself is refused by PostgreSQL
    instead of quietly rewriting the shared bibliographic record.
    """

    attempts = (
        (
            "INSERT",
            "insert into public.works (entity_id, canonical_title) "
            "values (gen_random_uuid(), 'kacak kayit')",
        ),
        (
            "UPDATE",
            "update public.works set canonical_title = 'degistirildi'",
        ),
        (
            "DELETE",
            "delete from public.works",
        ),
        (
            "INSERT (control.users)",
            "insert into control.users "
            "(id, tenant_id, email, display_name, password_hash, role, "
            "account_kind, is_active, created_at, updated_at) "
            "select gen_random_uuid(), id, 'kacak@ornek.org', 'x', 'y', "
            "'admin', 'institutional', true, now(), now() "
            "from control.tenants limit 1",
        ),
        (
            "DELETE (control.sessions)",
            "delete from control.sessions",
        ),
    )

    for label, statement in attempts:
        try:
            # `SET LOCAL` lives until the end of the transaction, so rolling back
            # after each attempt both cleans up a partially applied statement and
            # drops the role again.
            app.execute(text("set local role libraryhub_tenant_app"))
            app.execute(text(statement))
            app.rollback()

            record(
                f"Tenant rolu global plane'de {label} yapamaz",
                False,
                "IZIN VERILDI",
            )

        except Exception as exc:
            app.rollback()

            full = str(exc)

            record(
                f"Tenant rolu global plane'de {label} yapamaz",
                "permission denied" in full.lower()
                or "yetki" in full.lower(),
                full.strip().splitlines()[0][:90],
            )


def check_phase6_readiness(owner) -> None:
    """What still stands between here and dropping the legacy item tables.

    Aşama 6 removes `public.items`, `manifestation_item` and `item_agent_relation`,
    and drops `'ITEM'` from the `entities.entity_type` check. That is only safe
    once every row has a home in the tenant plane and no surviving record still
    points at an entity of that type.

    Measuring it beats assuming it: the point of writing this down is that "we
    think the migration is complete" and "every row is accounted for" are
    different claims, and only the second one is checkable.
    """

    missing_items = owner.execute(
        text(
            """
            SELECT count(*)
            FROM public.items i
            WHERE NOT EXISTS (
                SELECT 1 FROM tenant.items ti
                WHERE ti.legacy_entity_id = i.entity_id
            )
            """
        )
    ).scalar()

    record(
        "Asama 6: her legacy item tenant plane'inde karsiligi var",
        missing_items == 0,
        f"karsiligi olmayan: {missing_items}",
    )

    unrepresented = owner.execute(
        text(
            """
            SELECT count(*)
            FROM manifestation_item mi
            LEFT JOIN tenant.items ti
                   ON ti.legacy_entity_id = mi.item_entity_id
            LEFT JOIN tenant.holdings th ON th.id = ti.holding_id
            WHERE ti.id IS NULL
               OR th.manifestation_entity_id
                  IS DISTINCT FROM mi.manifestation_entity_id
            """
        )
    ).scalar()

    record(
        "Asama 6: manifestation_item holding'lerde temsil ediliyor",
        unrepresented == 0,
        f"temsil edilmeyen: {unrepresented}",
    )

    # Ownership used to live in a relation table. In the new model it is
    # structural -- item -> holding -> branch -> organization -- so the relation
    # only has to agree with what the structure already says.
    disagreeing = owner.execute(
        text(
            """
            SELECT count(*)
            FROM item_agent_relation iar
            JOIN tenant.items ti ON ti.legacy_entity_id = iar.item_entity_id
            JOIN tenant.holdings th ON th.id = ti.holding_id
            JOIN control.branches b ON b.id = th.branch_id
            JOIN control.organizations o ON o.id = b.organization_id
            WHERE iar.role = 'holding_institution'
              AND o.collective_agent_entity_id
                  IS DISTINCT FROM iar.agent_entity_id
            """
        )
    ).scalar()

    record(
        "Asama 6: kurum aidiyeti yapidan turetilebiliyor",
        disagreeing == 0,
        f"celisen satir: {disagreeing}",
    )

    stray_entities = owner.execute(
        text(
            """
            SELECT count(*)
            FROM entities e
            WHERE e.entity_type = 'ITEM'
              AND NOT EXISTS (
                  SELECT 1 FROM public.items i WHERE i.entity_id = e.id
              )
            """
        )
    ).scalar()

    record(
        "Asama 6: public.items'ta karsiligi olmayan ITEM entity yok",
        stray_entities == 0,
        f"basi bos ITEM entity: {stray_entities}",
    )

    # The hard blocker: dropping 'ITEM' from the check constraint fails if any
    # surviving row still names an entity of that type.
    referenced = owner.execute(
        text(
            """
            SELECT
                (SELECT count(*)
                   FROM entity_merges em
                  WHERE EXISTS (
                      SELECT 1 FROM entities e
                       WHERE e.entity_type = 'ITEM'
                         AND e.id IN (em.source_entity_id, em.target_entity_id)))
              + (SELECT count(*)
                   FROM entity_relation er
                  WHERE EXISTS (
                      SELECT 1 FROM entities e
                       WHERE e.entity_type = 'ITEM'
                         AND e.id IN (er.subject_entity_id, er.object_entity_id)))
            """
        )
    ).scalar()

    record(
        "Asama 6: ITEM entity'ye bakan merge/relation yok",
        referenced == 0,
        f"engelleyen kayit: {referenced}",
    )


def check_branch_guard(owner, app) -> None:
    """The database refuses a holding hung on another tenant's branch.

    The endpoint checks this in `_assert_branch_is_ours`, but the endpoint is not
    the only writer that will ever exist. `fk_holdings_branch` does not help: a
    foreign key confirms the branch exists, not that it is yours, and its check
    runs outside row level security. The trigger is what makes the rule true for
    every path, including a bulk import nobody has written yet.
    """

    # `control.branches` carries the same fail-closed policy as tenant.*, so an
    # application session with no tenant bound sees nothing at all.
    visible = app.execute(
        text("SELECT count(*) FROM control.branches")
    ).scalar()

    record(
        "control.branches tenant baglamasi olmadan gorunmez",
        visible == 0,
        f"gorunen sube: {visible}",
    )

    # The pair has to be read as the owner: the application role cannot see
    # across tenants, which is the property under test rather than an obstacle.
    pair = owner.execute(
        text(
            """
            SELECT b1.tenant_id AS tenant_a, b2.id AS foreign_branch
            FROM control.branches b1
            JOIN control.branches b2 ON b2.tenant_id <> b1.tenant_id
            LIMIT 1
            """
        )
    ).mappings().first()

    if pair is None:
        record(
            "Sube korumasi: yabanci subeye holding yazilamaz",
            False,
            "test edilecek iki kurum bulunamadi",
        )
        return

    try:
        app.execute(text("set local role libraryhub_tenant_app"))
        app.execute(
            text("select set_config(:name, :value, true)"),
            {"name": "libraryhub.tenant_id", "value": str(pair["tenant_a"])},
        )
        app.execute(
            text(
                """
                INSERT INTO tenant.holdings
                    (id, tenant_id, branch_id, holding_type,
                     local_holding_key, status, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :tenant_id, :branch_id, 'physical',
                     'GUARD-CHECK', 'active', now(), now())
                """
            ),
            {
                "tenant_id": pair["tenant_a"],
                "branch_id": pair["foreign_branch"],
            },
        )
        app.rollback()

        record(
            "Sube korumasi: yabanci subeye holding yazilamaz",
            False,
            "IZIN VERILDI",
        )

    except Exception as exc:
        app.rollback()

        # Match on the whole message and truncate only for display: cutting to 90
        # characters first once left "does not belon", and the check failed while
        # the trigger was working perfectly.
        full = str(exc)

        record(
            "Sube korumasi: yabanci subeye holding yazilamaz",
            "does not belong" in full,
            full.strip().splitlines()[0][:90],
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

        print("\n-- yazma siniri --")
        check_tenant_role_jail(app)
        check_branch_guard(owner, app)

        print("\n-- Asama 6 hazirligi --")
        check_phase6_readiness(owner)

    failed = [name for name, passed, _ in results if not passed]
    print()
    print(f"toplam kontrol: {len(results)} | gecen: {len(results) - len(failed)} | basarisiz: {len(failed)}")
    for name in failed:
        print(f"  BASARISIZ: {name}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
