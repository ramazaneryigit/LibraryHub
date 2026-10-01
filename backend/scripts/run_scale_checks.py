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

import json
import os
import sys
import time
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


def check_assertion_provenance(owner, app) -> None:
    """A claim can only be filed as its own source, and only a curator decides.

    The point of the provenance spine is that these two rules hold even if the
    application forgets them, so the check attacks the rules directly rather than
    going through the endpoints that already obey them.

    Everything happens inside a transaction that is rolled back, so the queue is
    left as it was found.
    """

    work_id = owner.execute(
        text("select entity_id from public.works order by canonical_title limit 1")
    ).scalar()

    sources = owner.execute(
        text(
            "select id, code from public.source_systems "
            "where code like 'tenant:%' order by code limit 2"
        )
    ).all()

    if work_id is None or len(sources) < 2:
        record(
            "Beyan kaynagi sahtekarligi reddediliyor",
            True,
            "denenecek iki kaynak yok; atlandi",
        )
        return

    mine, theirs = sources[0][0], sources[1][0]

    def attempt(source_id) -> str:
        """Try to file a claim; report the refusal.

        Each attempt gets its own savepoint. A rejected insert does not merely
        raise -- it aborts the surrounding transaction, and every later statement
        then fails with "current transaction is aborted", which would look like
        the second rule working when in fact nothing was tested.
        """

        nested = app.begin_nested()

        try:
            app.execute(
                text(
                    "insert into public.field_assertions "
                    "(id, entity_id, entity_type, field, value, source_system_id, "
                    " asserted_at, status) "
                    "values (gen_random_uuid(), :entity_id, 'WORK', "
                    "        'canonical_title', to_jsonb('sinama'::text), "
                    "        :source_id, now(), 'proposed')"
                ),
                {"entity_id": work_id, "source_id": source_id},
            )

            nested.commit()

            return "kabul edildi"

        except Exception as error:  # noqa: BLE001 - the refusal is the evidence
            nested.rollback()

            return type(error).__name__

    try:
        # 1. No source bound at all.
        app.execute(text("select set_config('libraryhub.source_system_id', '', true)"))
        unbound = attempt(mine)

        # 2. Bound as one source, claiming to be another.
        app.execute(
            text("select set_config(:n, :v, true)"),
            {"n": "libraryhub.source_system_id", "v": str(mine)},
        )
        forgery = attempt(theirs)

        # 3. A source may file its own claim...
        own = attempt(mine)

        # ...but may not approve it.
        nested = app.begin_nested()

        try:
            app.execute(
                text(
                    "update public.field_assertions set status = 'accepted' "
                    "where source_system_id = :source_id"
                ),
                {"source_id": mine},
            )
            nested.commit()
            self_approval = "kabul edildi"
        except Exception as error:  # noqa: BLE001
            nested.rollback()
            self_approval = type(error).__name__

        record(
            "Beyan kaynagi sahtekarligi reddediliyor",
            unbound != "kabul edildi"
            and forgery != "kabul edildi"
            and own == "kabul edildi"
            and self_approval != "kabul edildi",
            f"baglanmamis oturum={unbound}, "
            f"baskasi adina={forgery}, "
            f"kendi beyani={own}, "
            f"kendi kendini onaylama={self_approval}",
        )

    finally:
        app.rollback()


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


def check_view_covers_tenant_plane(owner) -> None:
    """The projection still shows every copy, now that it has no legacy branch.

    Before Aşama 6 this compared the view against `public.items` to prove the
    migration had carried everything across. That table is gone, so the question
    is the one that matters afterwards: is anything in the tenant plane missing
    from the global read?
    """

    compat = owner.execute(
        text("select count(*) from public.items_compat")
    ).scalar()

    missing = owner.execute(
        text(
            """
            SELECT count(*)
            FROM tenant.items ti
            WHERE NOT EXISTS (
                SELECT 1 FROM public.items_compat v
                WHERE v.entity_id = COALESCE(ti.legacy_entity_id, ti.id)
            )
            """
        )
    ).scalar()

    record(
        "Projeksiyon her nushayi gosteriyor",
        missing == 0,
        f"gorunum={compat}, eksik={missing}",
    )

    without_institution = owner.execute(
        text(
            """
            SELECT count(*)
            FROM public.items_compat
            WHERE holding_institution_entity_id IS NULL
            """
        )
    ).scalar()

    record(
        "Projeksiyonda kurumsuz nusha yok",
        without_institution == 0,
        f"kurumsuz: {without_institution}",
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


def check_fixtures_stay_within_themselves(owner) -> None:
    """A scale fixture may only ever point at a record it created itself.

    The generator used to link its holdings to the first twelve manifestations
    ordered by id, meaning real ones: 930 fixture holdings landed on genuine
    works and buried the libraries that actually hold them. A search for a novel
    returned ninety-two invented institutions and the two real ones were lost in
    the list, which is exactly what a reader notices and reports.

    Fixture records are identified by the marker their subtype row carries, so
    this compares each fixture holding's target against that set. Vacuously true
    when no fixtures are loaded, which is why the count of holdings examined is
    reported rather than just the verdict.
    """

    fixture_holdings = owner.execute(
        text(
            "select count(*) from tenant.holdings h "
            "join control.tenants t on t.id = h.tenant_id "
            "where t.slug like :prefix"
        ),
        {"prefix": "scale-%"},
    ).scalar()

    leaked = owner.execute(
        text(
            "select count(*) from tenant.holdings h "
            "join control.tenants t on t.id = h.tenant_id "
            "where t.slug like :prefix "
            "  and h.manifestation_entity_id is not null "
            "  and not exists ("
            "      select 1 from public.manifestations m "
            "      where m.entity_id = h.manifestation_entity_id "
            "        and m.notes like :marker)"
        ),
        {"prefix": "scale-%", "marker": "%[scale-fixture]%"},
    ).scalar()

    leaked += owner.execute(
        text(
            "select count(*) from tenant.holdings h "
            "join control.tenants t on t.id = h.tenant_id "
            "where t.slug like :prefix "
            "  and h.expression_entity_id is not null "
            "  and not exists ("
            "      select 1 from public.expressions x "
            "      where x.entity_id = h.expression_entity_id "
            "        and x.description like :marker)"
        ),
        {"prefix": "scale-%", "marker": "%[scale-fixture]%"},
    ).scalar()

    record(
        "Scale fixture kendi kaydindan baskasina baglanmiyor",
        leaked == 0,
        (
            f"{fixture_holdings} fixture holding incelendi, sizan: {leaked}"
            if fixture_holdings
            else "yuklu fixture yok (kontrol bos gecti)"
        ),
    )


def check_account_guard(app) -> None:
    """An application role cannot promote an account to administrator.

    The grant is real: `libraryhub_global_app` holds `INSERT, SELECT, UPDATE` on
    `control.users`, because the panel has to manage staff. So the guard trigger
    is the boundary, not the permission -- and it was declared `BEFORE INSERT`
    only, which left the same escalation one UPDATE away, plus the ability to
    rewrite an administrator's password without ever touching `role`.

    Both are attempted here. Neither has to be reachable from a route for this to
    matter: a write path that could reach `control.users` was enough, and the
    panel is that write path.
    """

    target = app.execute(
        text(
            "select id from control.users where role <> 'admin' "
            "order by email limit 1"
        )
    ).scalar()

    if target is None:
        record(
            "Uygulama rolu hesabi admin yapamaz",
            False,
            "sinanacak yonetici olmayan hesap yok",
        )
        return

    attempts = (
        (
            "Uygulama rolu hesabi admin yapamaz",
            "update control.users set role = 'admin' where id = :id",
        ),
        (
            "Uygulama rolu yoneticinin parolasini degistiremez",
            "update control.users set password_hash = 'x' "
            "where id = (select id from control.users "
            "            where role = 'admin' order by email limit 1)",
        ),
    )

    for label, sql in attempts:
        detail = ""

        try:
            with app.begin_nested():
                app.execute(text(sql), {"id": target})

            blocked = False
            detail = "IZIN VERILDI"

        except Exception as exc:
            blocked = True
            detail = str(exc).strip().splitlines()[0][:90]

        record(label, blocked, detail)


def check_legacy_retirement(owner) -> None:
    """The legacy item plane is gone, not merely unused.

    Before Aşama 6 these checks asked whether anything was still in the way. Now
    they ask whether it actually went -- a different question, and the one that
    can still fail quietly if a table survives a migration that was supposed to
    drop it.
    """

    for table in ("items", "manifestation_item", "item_agent_relation"):
        remaining = owner.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"public.{table}"},
        ).scalar()

        record(
            f"Asama 6: public.{table} dustu",
            remaining is None,
            f"kalan: {remaining}" if remaining else "yok",
        )

    item_entities = owner.execute(
        text("SELECT count(*) FROM entities WHERE entity_type = 'ITEM'")
    ).scalar()

    record(
        "Asama 6: ITEM entity kalmadi",
        item_entities == 0,
        f"kalan ITEM entity: {item_entities}",
    )

    allows_item = owner.execute(
        text(
            """
            SELECT pg_get_constraintdef(oid) LIKE '%ITEM%'
            FROM pg_constraint
            WHERE conname = 'ck_entities_entity_type'
            """
        )
    ).scalar()

    record(
        "Asama 6: entity_type artik ITEM kabul etmiyor",
        allows_item is False,
        "CHECK hala ITEM iceriyor" if allows_item else "temiz",
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


LEGACY_ITEM_TABLES = ("manifestation_item", "item_agent_relation")


def _sql_literals(path: Path) -> list[str]:
    """String literals in a file, excluding docstrings.

    SQL lives in strings and the legacy table names appear nowhere else except
    comments and prose. Scanning raw text flagged the comment that explained why
    a query had been removed -- the opposite of useful, and a tripwire that cries
    wolf is one people learn to ignore.
    """

    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))

    docstrings = set()

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        body = getattr(node, "body", [])

        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def check_legacy_item_surface() -> None:
    """Nothing writes global items, and nothing reads the tables phase 6 drops.

    Two questions with the same deadline. A POST under `/items` creates ITEM
    entities, which is what stops the entity type from being removable at all.
    And a route cannot outlive its table, so anything still reading
    `manifestation_item` or `item_agent_relation` has to move before those tables
    can go.

    Routers are found by importing every module in `app/routers`, so a route
    re-added anywhere is caught rather than only the two that used to exist.
    `app.main` is deliberately not imported: it mounts a static directory
    relative to the working directory and would fail from here.

    Reads are found by scanning rather than importing, because a query buried in
    a service is exactly as fatal as a route and much easier to overlook.
    """

    import importlib

    app_root = Path(__file__).resolve().parents[1] / "app"

    write_routes = []

    for path in sorted((app_root / "api" / "v1" / "routes").glob("*.py")):
        if path.stem.startswith("_"):
            continue

        module = importlib.import_module(f"app.api.v1.routes.{path.stem}")
        router = getattr(module, "router", None)

        if router is None:
            continue

        for route in router.routes:
            methods = getattr(route, "methods", set())

            if "POST" in methods and route.path.startswith("/items"):
                write_routes.append(f"POST {route.path}")

    record(
        "Asama 6: global item yazan uc kalmadi",
        not write_routes,
        (
            "hala acik: " + ", ".join(sorted(write_routes))
            if write_routes
            else "temiz"
        ),
    )

    readers = []

    for folder in ("api/v1/routes", "services"):
        for path in sorted((app_root / folder).rglob("*.py")):
            for literal in _sql_literals(path):
                for table in LEGACY_ITEM_TABLES:
                    if table in literal:
                        readers.append(f"{folder}/{path.name}:{table}")
                        break

    record(
        "Asama 6: legacy item tablosuna dokunan kod kalmadi",
        not readers,
        "hala dokunan: " + ", ".join(readers) if readers else "temiz",
    )


def check_subtype_insert_order(engine) -> None:
    """A subtype row and its entity can be written in one transaction.

    The database requires the `entities` row to exist before the `works` row that
    points at it, and SQLAlchemy orders its INSERTs across mappers that have no
    relationship between them by module-qualified class name. That accident held
    while every model lived in one module -- `app.models.Entity` sorts before
    `app.models.Work` -- and broke the moment the models were split by domain,
    because `app.db.models.bibliographic.Work` sorts before
    `app.db.models.identity.Entity`. Every create of a Work, Person, Concept,
    Expression, Manifestation, Place, TimeSpan, CollectiveAgent and
    ClassificationNode failed on the foreign key.

    A check rather than a test because the constraint is PostgreSQL's: on SQLite
    the ordering is unobservable and the suite cannot see it.
    """

    from sqlalchemy.orm import Session

    from app.core.ids import uuid7
    from app.db.models import Entity, Person, Work

    written = []

    try:
        with Session(engine) as session:
            work_id = uuid7()
            person_id = uuid7()
            written = [work_id, person_id]

            session.add(Entity(id=work_id, entity_type="WORK"))
            session.add(
                Work(
                    entity_id=work_id,
                    canonical_title="Siralama Sinamasi",
                    work_type="book",
                )
            )
            session.add(Entity(id=person_id, entity_type="PERSON"))
            session.add(
                Person(
                    entity_id=person_id,
                    canonical_name="Siralama Sinamasi",
                )
            )
            session.commit()

        record(
            "Alt tur yazimi ebeveyn entity'yi buluyor",
            True,
            "Work ve Person tek islemde yazildi",
        )

    except Exception as exc:
        record(
            "Alt tur yazimi ebeveyn entity'yi buluyor",
            False,
            str(exc).strip().splitlines()[0][:110],
        )

    finally:
        if written:
            with engine.begin() as connection:
                connection.execute(
                    text("delete from works where entity_id = any(:ids)"),
                    {"ids": written},
                )
                connection.execute(
                    text("delete from persons where entity_id = any(:ids)"),
                    {"ids": written},
                )
                connection.execute(
                    text("delete from entities where id = any(:ids)"),
                    {"ids": written},
                )
                # Last, and deliberately: the deletes above fire the outbox
                # triggers, so the events this check produces -- and the DELETE
                # events its own cleanup produces -- are only all present once
                # the rows are gone. The outbox is a log, and a check that writes
                # should not leave the table looking busier than the data.
                connection.execute(
                    text(
                        "delete from public.outbox_events "
                        "where aggregate_id = any(:ids)"
                    ),
                    {"ids": written},
                )


class _RollbackHere(Exception):
    """Raised to force a savepoint to roll back, and caught immediately."""


# Every table in `public` and `tenant` must either carry an outbox trigger or be
# named here with a reason. The point is not that this list is perfect -- it is a
# judgement -- but that adding a table forces somebody to make one. Without that,
# a new bibliographic table would simply never appear in the outbox, and the
# symptom would be a search index that is quietly missing a whole kind of record.
EXCUSED_FROM_OUTBOX = {
    "alembic_version": "migration bookkeeping",
    "outbox_events": "the table itself",
    # The index is derived, and watching it would loop: indexing writes
    # documents, which would raise events, which would index again.
    "search_documents": "derived; watching it would loop",
    # An assertion is metadata about a record, not the record. Accepting one
    # changes the canonical field, and *that* write is already watched -- so
    # watching the claim too would emit an event for a change that has not
    # happened yet.
    "field_assertions": "metadata about a record, not the record",
    "entities": "the registry; its subtypes carry the events",
    "source_systems": "ingestion input, not the catalogue",
    "source_records": "ingestion input, not the catalogue",
    "ingestion_batches": "ingestion input, not the catalogue",
    "reconciliation_candidates": "review queue; the writes it causes are covered",
    "reconciliation_decisions": "review queue; the writes it causes are covered",
    "source_classifications": "classification workflow, not the record",
    "classification_mappings": "classification workflow, not the record",
    "classification_validations": "classification workflow, not the record",
    "relation_predicates": "relation vocabulary, not relations",
    "relation_predicate_constraints": "relation vocabulary, not relations",
    "change_proposals": "a request, not the record; applying it is covered",
    "locations": "a shelf address, not something a reader searches for",
}


def check_outbox_same_transaction(owner) -> None:
    """An event and the change it describes commit or roll back together.

    This is the entire reason the table exists. An indexer may be behind, wrong
    or absent -- it can always be rebuilt from PostgreSQL. What it must never be
    is *inconsistent*: a change with no event is a row the index will never learn
    about, and no amount of retrying finds it. Writing the event in the same
    transaction is what rules that out, and the only way to show it is to roll a
    transaction back and look.
    """

    from app.core.ids import uuid7

    marker = uuid7()
    seen = None

    try:
        with owner.begin_nested():
            owner.execute(
                text(
                    "insert into public.entities "
                    "(id, entity_type, created_at, updated_at) "
                    "values (:id, 'WORK', now(), now())"
                ),
                {"id": marker},
            )
            owner.execute(
                text(
                    "insert into public.works "
                    "(entity_id, canonical_title, normalized_title, created_at) "
                    "values (:id, 'Outbox Sinamasi', 'outbox sinamasi', now())"
                ),
                {"id": marker},
            )

            seen = owner.execute(
                text(
                    "select count(*) from public.outbox_events "
                    "where aggregate_id = :id and event_type = 'INSERT'"
                ),
                {"id": marker},
            ).scalar()

            raise _RollbackHere

    except _RollbackHere:
        pass

    left = owner.execute(
        text("select count(*) from public.outbox_events where aggregate_id = :id"),
        {"id": marker},
    ).scalar()

    record(
        "Outbox: olay degisiklikle ayni islemde yaziliyor",
        seen == 1 and left == 0,
        f"islem icinde gorulen={seen}, geri alindiktan sonra kalan={left}",
    )


def check_outbox_reports_what_moved(owner) -> None:
    """An UPDATE says which columns changed, and only those.

    A consumer that only knows *that* a row changed has to re-read it. One that
    knows what moved can decide whether it needs to, which is the difference
    between an indexer that scales and one that rewrites every document on every
    touch.
    """

    from app.core.ids import uuid7

    marker = uuid7()
    changed = None

    try:
        with owner.begin_nested():
            owner.execute(
                text(
                    "insert into public.entities "
                    "(id, entity_type, created_at, updated_at) "
                    "values (:id, 'WORK', now(), now())"
                ),
                {"id": marker},
            )
            owner.execute(
                text(
                    "insert into public.works "
                    "(entity_id, canonical_title, normalized_title, "
                    " original_language, created_at) "
                    "values (:id, 'Ilk', 'ilk', 'tr', now())"
                ),
                {"id": marker},
            )
            owner.execute(
                text(
                    "update public.works set canonical_title = 'Ikinci' "
                    "where entity_id = :id"
                ),
                {"id": marker},
            )

            changed = owner.execute(
                text(
                    "select payload -> 'changed' from public.outbox_events "
                    "where aggregate_id = :id and event_type = 'UPDATE' "
                    "order by occurred_at desc limit 1"
                ),
                {"id": marker},
            ).scalar()

            raise _RollbackHere

    except _RollbackHere:
        pass

    # PSQL returns jsonb as text; both shapes are accepted so the check does not
    # depend on the driver.
    if isinstance(changed, str):
        changed = json.loads(changed)

    keys = sorted((changed or {}).keys())

    record(
        "Outbox: UPDATE yalnizca degisen sutunu bildiriyor",
        keys == ["canonical_title"],
        f"bildirilen sutunlar: {keys}",
    )


def check_outbox_coverage(owner) -> None:
    """Every table is either watched or explicitly excused."""

    rows = owner.execute(
        text(
            "select n.nspname || '.' || c.relname "
            "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where c.relkind = 'r' and n.nspname in ('public', 'tenant') "
            "order by 1"
        )
    ).scalars().all()

    watched = set(
        owner.execute(
            text(
                "select c.relname from pg_trigger t "
                "join pg_class c on c.oid = t.tgrelid "
                "where not t.tgisinternal and t.tgname like 'trg_%_outbox'"
            )
        )
        .scalars()
        .all()
    )

    undecided = sorted(
        name
        for name in rows
        if name.split(".", 1)[1] not in watched
        and name.split(".", 1)[1] not in EXCUSED_FROM_OUTBOX
    )

    record(
        "Outbox: her tablo izleniyor ya da gerekcesiyle muaf",
        not undecided,
        (
            f"{len(watched)} tablo izleniyor, {len(EXCUSED_FROM_OUTBOX)} muaf"
            if not undecided
            else "karar verilmemis: " + ", ".join(undecided)
        ),
    )


def check_nomen_normalization(owner) -> None:
    """Every name with a value has a comparable form derived from it.

    `nomens.normalized_value` is filled by an ORM event rather than a trigger, and
    that is a deliberate trade. The normalization is NFKD, then casefold, then
    combining-mark removal, then punctuation to spaces; this PostgreSQL image has
    no `unaccent`, so doing it in plpgsql would mean a second implementation of
    one decision -- free to disagree with the first exactly where Turkish needs it
    most, on the dotted and dotless i that `casefold` and `lower` already treat
    differently.

    The price of that choice is this check. An event listener only covers writes
    that go through the ORM, so a later raw-SQL insert would leave the column
    empty and the name would quietly stop being findable by anybody who typed it
    without the accents.
    """

    total, filled, empty = owner.execute(
        text(
            "select count(*), count(normalized_value), "
            "count(*) filter (where value is not null "
            "                   and normalized_value is null) "
            "from public.nomens"
        )
    ).one()

    # And the point of the column: an identical name now scores against a
    # normalized probe the way it should. Before, PostgreSQL folded one side with
    # `lower()` and the probe arrived fully normalized, so `Ayşe Demir` scored
    # 0.571 against a probe of itself.
    score = owner.execute(
        text(
            "select similarity(normalized_value, 'ayse demir') "
            "from public.nomens where value = 'Ayşe Demir' limit 1"
        )
    ).scalar()

    if score is None:
        record(
            "Nomen: normalize edilmis bicim dolu ve dogru",
            empty == 0,
            f"{filled}/{total} dolu, bos kalan {empty} (sinanacak isim yok)",
        )
        return

    record(
        "Nomen: normalize edilmis bicim dolu ve dogru",
        empty == 0 and float(score) >= 0.999,
        f"{filled}/{total} dolu, bos kalan {empty}, "
        f"birebir ayni isim skoru {float(score):.3f}",
    )


def check_holdings_reach_the_catalogue(owner) -> None:
    """Every holding is visible as a library, whether or not it has copies.

    The institution is a property of the holding -- `holdings.branch_id` ->
    `branches.organization_id` -> `organizations.collective_agent_entity_id` --
    and it used to be read off the *items* instead. So a library that had
    catalogued the holding but not the individual copies was absent from the
    union catalogue. Measured when this was found: six of sixteen holdings had no
    items, a third of the libraries, including ones holding works that other
    libraries' holdings also cover.

    That is not an edge case: it is a serial, a donation not yet itemised, or a
    migration that moved holdings before items -- which is what the `migrated-*`
    rows are. At a thousand libraries the missing third is the catalogue.

    Both numbers are reported, because "no holding is missing" and "some holdings
    have no institution recorded" are different facts and only the first is a
    failure. A holding with no organization is an incomplete record, not a
    library, and the reader is told so rather than shown a blank name.
    """

    total = owner.execute(
        text("select count(*) from tenant.holdings")
    ).scalar()

    suppressed = owner.execute(
        text(
            "select count(*) from tenant.holdings where status = 'suppressed'"
        )
    ).scalar()

    published = total - suppressed

    projected = owner.execute(
        text("select count(*) from public.holdings_compat")
    ).scalar()

    without_items = owner.execute(
        text(
            "select count(*) from public.holdings_compat where item_count = 0"
        )
    ).scalar()

    without_institution = owner.execute(
        text(
            "select count(*) from public.holdings_compat "
            "where holding_institution_entity_id is null"
        )
    ).scalar()

    # Two different failures, and both matter. A published holding that is not in
    # the projection is a library missing from the union catalogue -- the defect
    # that started this. A holding that *is* in it with no institution is a
    # catalogue entry pointing nowhere, which is what the migration bucket was
    # before it was suppressed. Neither is allowed to be non-zero.
    record(
        "Her yayinlanmis holding toplu katalogda ve kurumlu",
        published == projected and without_institution == 0,
        f"{projected}/{published} yayinlanmis holding yansitildi "
        f"({suppressed} bastirilmis), "
        f"{without_items} tanesi nushasiz, "
        f"{without_institution} tanesinde kurum kaydi yok",
    )


def check_search_index_is_reproducible(owner) -> None:
    """A rebuilt index equals the one the outbox maintained.

    §9.3 in one assertion. The index is allowed to be stale, partial or wrong --
    it is never the source of truth -- but it must be reproducible. So the check
    corrupts it on purpose, feeds it the outbox, and compares what it then holds
    against a full rebuild. If those two disagree, one of the two paths is wrong
    and a search result is quietly lying.

    It writes a title, and puts it back, because the incremental path can only be
    tested by making a change. That write is also the reason the check is worth
    having: it proves the index does *not* move until the indexer runs, which is
    what stops the source tables and the index drifting apart unnoticed.
    """

    import hashlib

    from app.services.search_index import consume, index, reindex

    def fingerprint() -> str:
        digest = hashlib.sha256()

        for row in owner.execute(
            text(
                "select entity_id, entity_type, label, body, work_ids "
                "from public.search_documents order by entity_id"
            )
        ).all():
            digest.update("|".join(str(value) for value in row).encode("utf-8"))

        return digest.hexdigest()[:16]

    target = owner.execute(
        text("select entity_id from public.works order by entity_id limit 1")
    ).scalar()

    original = owner.execute(
        text("select canonical_title from public.works where entity_id = :id"),
        {"id": target},
    ).scalar()

    marker = "Reindex Sinama Baskisi"

    try:
        reindex(owner)
        baseline = fingerprint()

        owner.execute(
            text("update public.works set canonical_title = :title where entity_id = :id"),
            {"title": marker, "id": target},
        )

        # The index must still be behind: the write fired an outbox event and
        # nothing has consumed it.
        stale = owner.execute(
            text(
                "select count(*) from public.search_documents "
                "where entity_id = :id and body like :marker"
            ),
            {"id": target, "marker": f"%reindex sinama baskisi%"},
        ).scalar()

        consume(owner)
        incremental = fingerprint()

        after = owner.execute(
            text(
                "select count(*) from public.search_documents "
                "where entity_id = :id and body like :marker"
            ),
            {"id": target, "marker": "%reindex sinama baskisi%"},
        ).scalar()

        reindex(owner)
        rebuilt = fingerprint()

        record(
            "Arama indeksi yeniden uretilebilir",
            stale == 0 and after == 1 and incremental == rebuilt,
            f"tuketim oncesi bayat={stale}, sonrasi={after}, "
            f"artimli={incremental} yeniden={rebuilt} "
            f"(baslangic {baseline})",
        )

    finally:
        owner.execute(
            text("update public.works set canonical_title = :title where entity_id = :id"),
            {"title": original, "id": target},
        )

        consume(owner)
        index(owner, [target])


def check_search_index_is_complete(owner) -> None:
    """Every work has a document, and no document is empty.

    A work with no document is a title nobody can find, and the failure is
    invisible from the search side: the query returns fewer rows and nothing says
    which ones are missing.

    Documents that resolve to no work are *reported*, not failed. A person who
    has written nothing is a legitimate entity with nothing to resolve to, and
    calling that a defect would train the reader to ignore the line.
    """

    works = owner.execute(text("select count(*) from public.works")).scalar()

    documents = owner.execute(
        text(
            "select count(*) from public.search_documents where entity_type = 'WORK'"
        )
    ).scalar()

    empty_bodies = owner.execute(
        text(
            "select count(*) from public.search_documents "
            "where body = '' and entity_type = 'WORK'"
        )
    ).scalar()

    empty_others = owner.execute(
        text(
            "select count(*) from public.search_documents "
            "where body = '' and entity_type <> 'WORK'"
        )
    ).scalar()

    unreachable = owner.execute(
        text(
            "select count(*) from public.search_documents "
            "where cardinality(work_ids) = 0"
        )
    ).scalar()

    record(
        "Arama indeksi eksiksiz",
        works == documents and empty_bodies == 0,
        f"{documents}/{works} eser belgesi, {empty_bodies} bos eser govdesi; "
        f"{empty_others} diger bos govde (ifade hakkinda henuz bir sey "
        f"bilinmiyor olabilir), "
        f"{unreachable} belge hicbir esere ulasmiyor (kisi/kavram olabilir)",
    )


def check_search_finds_what_it_should(owner) -> None:
    """Anything a reader could type finds the work it belongs to.

    `/search` no longer walks twenty joins; it looks a probe up in the index. That
    is only safe if the index can find everything the old query could, so this
    asks the two ends of the question directly: every work by its own title, and
    every copy by its own barcode.

    A missing title is a work nobody can find, and the symptom is invisible from
    the search side -- the query simply returns fewer rows and nothing says which
    one is absent. That is why this is a check and not a hope.
    """

    from app.services.search_index import reindex, search

    # The index this asserts about has to be current first.
    reindex(owner)

    missing_titles = []

    for entity_id, title in owner.execute(
        text(
            "select entity_id, canonical_title from public.works "
            "where canonical_title is not null "
            "order by canonical_title"
        )
    ).all():
        if entity_id not in search(owner, title, limit=200):
            missing_titles.append(title[:36])

    missing_barcodes = []

    # The index resolves a copy to the *work*, not to the manifestation, so the
    # comparison has to be against the work the copy's manifestation belongs to.
    # Comparing a manifestation id against work ids is the mistake this check
    # made on its first run, and it reported ten barcodes as missing that were
    # findable all along.
    for barcode, work_ids in owner.execute(
        text(
            "select v.barcode, array_agg(distinct we.work_entity_id) "
            "from public.items_compat v "
            "join public.expression_manifestation em "
            "  on em.manifestation_entity_id = v.manifestation_entity_id "
            "join public.work_expression we "
            "  on we.expression_entity_id = em.expression_entity_id "
            "where v.barcode is not null and v.barcode <> '' "
            "group by v.barcode "
            "order by v.barcode"
        )
    ).all():
        found = set(search(owner, barcode, limit=200))

        if not found.intersection(work_ids):
            missing_barcodes.append(barcode[:36])

    record(
        "Arama indekste ne varsa onu buluyor",
        not missing_titles and not missing_barcodes,
        (
            f"{len(missing_barcodes)} barkod ve {len(missing_titles)} baslik "
            "bulunamadi: "
            + ", ".join((missing_titles + missing_barcodes)[:3])
            if (missing_titles or missing_barcodes)
            else "her baslik ve her barkod kendi eserini buluyor"
        ),
    )


# §15.2 defers partitioning with a measured trigger: about fifty million rows, or
# a p95 above 100 ms on `entity_relation`. Both are checked below.
PARTITION_ROW_THRESHOLD = 50_000_000
PARTITION_LATENCY_THRESHOLD_MS = 100.0


def check_partitioning_threshold(owner) -> None:
    """§15.2 says partitioning waits. This is what says whether it still does.

    The section is explicit -- "not today", with a trigger of ~50 million rows or
    a p95 over 100 ms on `entity_relation` -- so the useful work here is not
    rewriting a table with seventy-nine rows. It is making the trigger a
    measurement that fails a check, so the decision is enforced by the numbers
    rather than remembered by whoever reads the section last.

    Measuring it also turned up what the plan did not account for. PostgreSQL
    requires the partition key in every unique constraint, so `PARTITION BY LIST
    (entity_type)` on `entities` forces the primary key to `(id, entity_type)`,
    which forces all nineteen foreign keys that point at `entities(id)` to be
    rewritten and their tables to grow an `entity_type` column. `PARTITION BY
    HASH (id)` would leave every one of them alone, because `id` is already the
    key -- but it buys none of the type-scan benefit the section wanted.

    So the plan is not wrong to wait; it is wrong about which partition to build
    first. `entity_relation` can be partitioned by `subject_entity_id` today at
    no cost to anything, since its unique constraint already contains that
    column. `entities` cannot be partitioned by type without a schema-wide
    change, and that is a decision to take deliberately rather than as a
    performance tweak.
    """

    entities = owner.execute(text("select count(*) from public.entities")).scalar()
    relations = owner.execute(
        text("select count(*) from public.entity_relation")
    ).scalar()

    referencing = owner.execute(
        text(
            "select count(*) from pg_constraint "
            "where contype = 'f' and confrelid = 'public.entities'::regclass"
        )
    ).scalar()

    # The query §15.1 added an index for, which is the one that grows: relations
    # are read in both directions and the reverse scan is the hot one.
    samples = []

    for _ in range(20):
        start = time.perf_counter()

        owner.execute(
            text(
                "select count(*) from public.entity_relation "
                "where predicate = 'has_subject' "
                "  and object_entity_id is not null"
            )
        ).scalar()

        samples.append((time.perf_counter() - start) * 1000)

    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]

    rows_triggered = max(entities, relations) >= PARTITION_ROW_THRESHOLD
    latency_triggered = p95 >= PARTITION_LATENCY_THRESHOLD_MS

    record(
        "Bolumleme esigi asilmadi (§15.2)",
        not rows_triggered and not latency_triggered,
        f"entities={entities} entity_relation={relations} "
        f"(esik {PARTITION_ROW_THRESHOLD}), p95={p95:.1f} ms "
        f"(esik {PARTITION_LATENCY_THRESHOLD_MS:.0f} ms), "
        f"entities'e bakan FK={referencing}",
    )


def check_outbox_is_being_drained(owner) -> None:
    """Is the catalogue current, or is the index drifting behind?

    The worker logs its lag every pass, but a log is read by whoever happens to be
    looking. This is the same number asserted, so "the search index is a few
    seconds behind" is a fact the checks know rather than a belief.

    The failure condition is deliberately not "pending > 0": between a library's
    write and the worker's next pass there are *always* pending events, and a check
    that fails on the normal state is a check people learn to ignore. It fails when
    a backlog is *old* -- which is what a stopped or wedged worker looks like, and
    a running worker that is an hour behind is worse than a stopped one because it
    looks healthy.
    """

    pending, oldest = owner.execute(
        text(
            "select count(*), "
            "       extract(epoch from (now() - min(occurred_at))) "
            "from public.outbox_events where published_at is null"
        )
    ).one()

    lag_seconds = float(oldest) if oldest is not None else 0.0
    threshold = 120.0

    record(
        "Outbox tuketiliyor (isci calisiyor)",
        lag_seconds < threshold,
        f"bekleyen={pending}, en eski olay={lag_seconds:.1f}s "
        f"(esik {threshold:.0f}s)",
    )


def check_app_imports_resolve() -> None:
    """Every absolute `app.*` import in the source points at something real.

    The models moved into `app/db/models/` and three modules were renamed into
    `app/core/`. Two absolute imports were missed, both in files that nothing
    else imports: a script, and an Alembic revision. Neither the test suite nor a
    reading of the diff would have found them -- one is only ever run by hand, and
    the other had already been applied on this database.

    The revision is the reason this is a check at all. Its imports are resolved
    when the revision *runs*, so a database built from scratch would have stopped
    dead partway through the migration history -- while this one, already past
    that step, worked perfectly and said nothing.

    Only absolute `app.*` imports are covered here. Relative imports inside the
    package are proven by the application starting, which every other check in
    this file already depends on.
    """

    import ast
    import importlib.util

    backend = Path(__file__).resolve().parents[1]
    missing = []

    for path in sorted(backend.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue

            if node.module != "app" and not node.module.startswith("app."):
                continue

            try:
                found = importlib.util.find_spec(node.module)
            except (ImportError, ValueError):
                found = None

            if found is None:
                missing.append(
                    f"{path.relative_to(backend).as_posix()}:{node.lineno} "
                    f"{node.module}"
                )

    record(
        "Her app.* import gercek bir modulu gosteriyor",
        not missing,
        "; ".join(missing[:4]) if missing else "temiz",
    )


def main() -> int:
    owner_engine = create_engine(OWNER_URL)
    app_engine = create_engine(APP_URL)

    print("Ölçek senaryo kontrolleri\n")

    with owner_engine.connect() as owner, app_engine.connect() as app:
        print("\n-- yalitkanlik --")
        check_rls_isolation(owner, app)
        check_rls_fail_closed(app)

        print("\n-- butunluk --")
        check_no_orphans(owner)
        check_barcode_uniqueness(owner)
        check_view_covers_tenant_plane(owner)

        print("\n-- index ve plan --")
        check_indexes(owner)

        print("\n-- mimari sorusu --")
        check_manifestation_reach(owner)

        print("\n-- yazma siniri --")
        check_tenant_role_jail(app)
        check_branch_guard(owner, app)
        check_account_guard(app)

        print("\n-- yazma yolu --")
        check_subtype_insert_order(owner_engine)
        check_fixtures_stay_within_themselves(owner)

        print("\n-- kaynak tutarliligi --")
        check_app_imports_resolve()
        check_nomen_normalization(owner)
        check_holdings_reach_the_catalogue(owner)

        print("\n-- arama indeksi --")
        check_search_index_is_complete(owner)
        check_search_index_is_reproducible(owner)
        check_search_finds_what_it_should(owner)

        print("\n-- olcek --")
        check_partitioning_threshold(owner)
        check_outbox_is_being_drained(owner)

        print("\n-- provenance --")
        check_assertion_provenance(owner, app)

        print("\n-- outbox --")
        check_outbox_same_transaction(owner)
        check_outbox_reports_what_moved(owner)
        check_outbox_coverage(owner)

        print("\n-- Asama 6 dogrulamasi --")
        check_legacy_item_surface()
        check_legacy_retirement(owner)

    failed = [name for name, passed, _ in results if not passed]
    print()
    print(f"toplam kontrol: {len(results)} | gecen: {len(results) - len(failed)} | basarisiz: {len(failed)}")
    for name in failed:
        print(f"  BASARISIZ: {name}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
