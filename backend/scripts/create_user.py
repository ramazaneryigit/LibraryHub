"""Create a staff account, or reset its password.

Why this still exists next to the panel
---------------------------------------
The application role **does** hold `INSERT, SELECT, UPDATE` on `control.users` --
that is what lets `/api/v1/admin/users` manage staff at all -- so the boundary is
not the grant. It is the guard trigger, which refuses an application role any
administrator account and any account that is already verified.

Two things are therefore out of the panel's reach, and both are here:

* creating or changing an **administrator**, the account that can write the
  shared plane;
* marking an address **verified**, which is the panel's deliberate shortfall: an
  account it opens is confirmed by its holder.

Run with the owner credential, which the trigger exempts.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python create_user.py \\
        --email katalog@kku.edu.tr \\
        --name 'Kirikkale Katalog' \\
        --tenant k-r-kkale-niversitesi-6e788275 \\
        --role librarian"

Omit `--password` to be prompted (needs an interactive terminal, so drop `-T`).
Pass it and the value lands in your shell history -- acceptable for a local
development account, not for anything real.

    ... python create_user.py --list

A platform administrator
------------------------
`--platform` opens an account with no tenant. It curates the shared record --
reviewing proposals, merging identities, loading batches -- which belongs to no
institution, and it is the only account kind that may omit `--tenant`. The role is
forced to `admin`, and `tenant_db` refuses it, so it cannot reach the tenant plane
at all (docs/architecture-v2.md §0.20).

    ... python create_user.py --platform \\
        --email platform@libraryhub.local \\
        --name 'Platform Yoneticisi'

See also `docs/architecture-v2.md` §0.21 and §0.22: the curation endpoints, and
what the panel may do to accounts.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.core.security import hash_password
from app.email_domains import classify_email
from app.core.ids import uuid7


ROLES = ("admin", "librarian", "viewer")


def list_users(connection) -> None:
    # `left join`, not `join`: a platform administrator has no tenant, and an
    # inner join would hide exactly the accounts that are hardest to find.
    rows = connection.execute(
        text(
            """
            select u.email, u.display_name, u.role, u.is_active,
                   t.slug as tenant_slug, count(s.id) as aktif_oturum
            from control.users u
            left join control.tenants t on t.id = u.tenant_id
            left join control.sessions s
                   on s.user_id = u.id
                  and s.revoked_at is null
                  and s.expires_at > now()
            group by u.id, t.slug
            order by t.slug nulls first, u.email
            """
        )
    ).fetchall()

    if not rows:
        print("Kayıtlı kullanıcı yok.")
        return

    print(f"{len(rows)} kullanıcı:\n")
    for email, name, role, active, tenant_slug, sessions in rows:
        flag = "" if active else " (PASIF)"
        where = tenant_slug or "(platform)"
        print(f"  {email:34} {role:10} {where:48} oturum={sessions}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--tenant", help="tenant slug")
    parser.add_argument("--role", default="librarian", choices=ROLES)
    parser.add_argument(
        "--kind",
        choices=("institutional", "corporate"),
        help="override the account kind inferred from the domain",
    )
    parser.add_argument(
        "--principal-kind",
        default=None,
        choices=(
            "platform",
            "tenant_staff",
            "academician",
            "publisher",
            "isbn_agency",
            "vendor",
        ),
        help=(
            "which participant this account is; inferred as 'tenant_staff' "
            "when a tenant is given and 'platform' when --platform is used"
        ),
    )
    parser.add_argument("--password", help="omit to be prompted")
    parser.add_argument(
        "--platform",
        action="store_true",
        help="no tenant: a platform administrator (forces --role admin)",
    )
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.list:
            list_users(connection)
            return 0

        missing = [
            flag
            for flag, value in (
                ("--email", args.email),
                ("--name", args.name),
            )
            if not value
        ]

        if missing:
            parser.error(f"gerekli: {', '.join(missing)} (veya --list)")

        # The four participants who are not libraries -- an academician, a
        # publisher, the ISBN agency, a vendor -- are tenant-less by nature but are
        # not the platform either. Before this they could not be created at all,
        # because a missing tenant meant a platform administrator.
        #
        # Stated once, and the older check that demanded `--platform` for every
        # tenant-less account is gone: it was right when the platform was the only
        # such participant, and it is what stops `--principal-kind isbn_agency`
        # from working at all.
        tenant_less_participant = bool(
            args.principal_kind and args.principal_kind != "tenant_staff"
        )

        if args.platform and args.tenant:
            parser.error(
                "--platform ve --tenant birlikte kullanilamaz: platform hesabi "
                "hicbir kutuphaneye bagli degildir"
            )

        if tenant_less_participant:
            if args.platform:
                parser.error(
                    "--platform ile --principal-kind birlikte kullanilamaz: "
                    "platform hesabi 'platform'dir"
                )

            if args.tenant:
                parser.error(
                    f"'{args.principal_kind}' bir kutuphaneye bagli degildir; "
                    "--tenant vermeyin"
                )
        elif not args.platform and not args.tenant:
            parser.error("gerekli: --tenant (veya --platform)")

        role = args.role

        if args.platform:
            if args.role != "admin":
                print("NOT: platform hesabi daima 'admin'; --role yok sayildi.")

            role = "admin"

        email = args.email.strip().lower()

        # Same rule as self-registration, unless an administrator overrides it:
        # an account opened on a university domain is institutional, one on a
        # company domain is corporate. A domain that neither classifies -- a free
        # mail address an administrator chose to use for a test account -- is
        # reported rather than silently guessed at.
        detected, refusal = classify_email(email)

        if args.kind:
            account_kind = args.kind
        elif detected:
            account_kind = detected
        else:
            account_kind = "institutional"
            print(f"UYARI: {refusal}")
            print(
                f"  '{email}' otomatik siniflandirilamadi; "
                f"'{account_kind}' varsayildi. --kind ile degistirebilirsiniz."
            )

        tenant_id = None

        # A participant who is not a library -- a publisher, an academician, the
        # ISBN agency, a vendor -- has no tenant, and is not the platform either.
        # Without this the lookup below runs with `--tenant` unset, finds nothing,
        # prints the list of tenants that do exist and creates no account at all,
        # which is what it did every time this was attempted.
        if not args.platform and not tenant_less_participant:
            tenant_id = connection.execute(
                text("select id from control.tenants where slug = :slug"),
                {"slug": args.tenant},
            ).scalar()

            if tenant_id is None:
                print(f"Tenant bulunamadi: {args.tenant}")
                print("Mevcut tenant'lar:")
                for slug, name in connection.execute(
                    text(
                        "select slug, display_name from control.tenants "
                        "order by slug"
                    )
                ).fetchall():
                    print(f"  {slug:48} {name}")
                return 1

        # `principal_kind` is computed further down, next to the insert; this only
        # needs a label for the confirmation line, and reaching for the variable
        # before it exists is what raised UnboundLocalError here.
        target = (
            "(platform)"
            if args.platform
            else (args.tenant or args.principal_kind or "katilimci")
        )

        password = args.password

        if not password:
            password = getpass.getpass("Parola: ")
            confirm = getpass.getpass("Parola (tekrar): ")

            if password != confirm:
                print("Parolalar uyusmuyor.")
                return 1

        if not password:
            print("Parola bos olamaz.")
            return 1

        existing = connection.execute(
            text("select id from control.users where email = :email"),
            {"email": email},
        ).scalar()

        password_hash = hash_password(password)

        # Which participant this account is. Until now every account was staff or
        # the platform, so the constraint allowed the two by accident of a missing
        # tenant; it is stated here so an ISBN agency account is not silently
        # recorded as library staff, which is what the column default would do.
        principal_kind = args.principal_kind

        if principal_kind is None:
            principal_kind = "platform" if args.platform else "tenant_staff"

        if principal_kind != "tenant_staff" and args.tenant and not args.platform:
            parser.error(
                f"'{principal_kind}' bir kutuphaneye bagli degildir; "
                "--tenant vermeyin"
            )

        # `role` says what somebody may do *inside* a library, and a publisher or
        # an academician is not inside one. The database refuses the combination
        # as well; refusing it here means the operator gets a sentence instead of
        # a constraint violation.
        if principal_kind not in ("tenant_staff", "platform") and role == "admin":
            parser.error(
                f"'{principal_kind}' hesabi 'admin' olamaz: rol, bir kutuphane "
                "icinde ne yapilabilecegini soyler ve bu hesap bir kutuphanenin "
                "icinde degil. --role viewer veya librarian kullanin."
            )

        if existing is None:
            connection.execute(
                text(
                    """
                    insert into control.users
                        (id, tenant_id, email, display_name, password_hash,
                         role, account_kind, principal_kind, email_verified_at,
                         is_active, created_at, updated_at)
                    values
                        (:id, :tenant_id, :email, :name, :password_hash,
                         :role, :account_kind, :principal_kind, now(), true,
                         now(), now())
                    """
                ),
                {
                    "id": uuid7(),
                    "tenant_id": tenant_id,
                    "email": email,
                    "name": args.name,
                    "password_hash": password_hash,
                    "role": role,
                    "account_kind": account_kind,
                    "principal_kind": principal_kind,
                },
            )

            print(
                f"Kullanici olusturuldu: {email} ({role}, "
                f"{account_kind}) -> {target}"
            )
            print("  e-posta dogrulanmis sayildi: hesabi yonetici acti")
        else:
            connection.execute(
                text(
                    """
                    update control.users
                    set password_hash = :password_hash,
                        display_name = :name,
                        role = :role,
                        account_kind = :account_kind,
                        principal_kind = :principal_kind,
                        is_active = true,
                        email_verified_at = coalesce(email_verified_at, now()),
                        updated_at = now()
                    where id = :id
                    """
                ),
                {
                    "id": existing,
                    "password_hash": password_hash,
                    "name": args.name,
                    "role": role,
                    "account_kind": account_kind,
                    "principal_kind": principal_kind,
                },
            )

            revoked = connection.execute(
                text(
                    """
                    update control.sessions
                    set revoked_at = now()
                    where user_id = :id and revoked_at is null
                    """
                ),
                {"id": existing},
            ).rowcount

            print(f"Kullanici guncellendi: {email} ({role}) -> {target}")
            print(f"  iptal edilen oturum: {revoked}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
