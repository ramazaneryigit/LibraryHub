"""Create a staff account, or reset its password.

Why this is not an API endpoint
-------------------------------
Only the schema owner can write to `control.users`; the application role has
`SELECT` on it and nothing else. Creating accounts is therefore an administrative
act performed with the owner credential, not something a stolen application
session can do. Giving the application `INSERT` on accounts "for an admin panel"
would mean one compromised session can mint more sessions with any tenant.

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
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.auth import hash_password
from app.ids import uuid7


ROLES = ("admin", "librarian", "viewer")


def list_users(connection) -> None:
    rows = connection.execute(
        text(
            """
            select u.email, u.display_name, u.role, u.is_active,
                   t.slug as tenant_slug, count(s.id) as aktif_oturum
            from control.users u
            join control.tenants t on t.id = u.tenant_id
            left join control.sessions s
                   on s.user_id = u.id
                  and s.revoked_at is null
                  and s.expires_at > now()
            group by u.id, t.slug
            order by t.slug, u.email
            """
        )
    ).fetchall()

    if not rows:
        print("Kayıtlı kullanıcı yok.")
        return

    print(f"{len(rows)} kullanıcı:\n")
    for email, name, role, active, tenant_slug, sessions in rows:
        flag = "" if active else " (PASIF)"
        print(f"  {email:34} {role:10} {tenant_slug:48} oturum={sessions}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--tenant", help="tenant slug")
    parser.add_argument("--role", default="librarian", choices=ROLES)
    parser.add_argument("--password", help="omit to be prompted")
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
                ("--tenant", args.tenant),
            )
            if not value
        ]

        if missing:
            parser.error(f"gerekli: {', '.join(missing)} (veya --list)")

        email = args.email.strip().lower()

        tenant_id = connection.execute(
            text("select id from control.tenants where slug = :slug"),
            {"slug": args.tenant},
        ).scalar()

        if tenant_id is None:
            print(f"Tenant bulunamadi: {args.tenant}")
            print("Mevcut tenant'lar:")
            for slug, name in connection.execute(
                text("select slug, display_name from control.tenants order by slug")
            ).fetchall():
                print(f"  {slug:48} {name}")
            return 1

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

        if existing is None:
            connection.execute(
                text(
                    """
                    insert into control.users
                        (id, tenant_id, email, display_name, password_hash,
                         role, is_active, created_at, updated_at)
                    values
                        (:id, :tenant_id, :email, :name, :password_hash,
                         :role, true, now(), now())
                    """
                ),
                {
                    "id": uuid7(),
                    "tenant_id": tenant_id,
                    "email": email,
                    "name": args.name,
                    "password_hash": password_hash,
                    "role": args.role,
                },
            )

            # A password change should not leave old sessions alive.
            print(f"Kullanici olusturuldu: {email} ({args.role}) -> {args.tenant}")
        else:
            connection.execute(
                text(
                    """
                    update control.users
                    set password_hash = :password_hash,
                        display_name = :name,
                        role = :role,
                        is_active = true,
                        updated_at = now()
                    where id = :id
                    """
                ),
                {
                    "id": existing,
                    "password_hash": password_hash,
                    "name": args.name,
                    "role": args.role,
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

            print(f"Kullanici guncellendi: {email} ({args.role}) -> {args.tenant}")
            print(f"  iptal edilen oturum: {revoked}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
