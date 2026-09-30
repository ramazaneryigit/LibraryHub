"""Complete an email verification from the console.

There is no mail sender wired up yet. `POST /auth/register` writes the
verification link to the application log -- which is what a development mailer
does -- and this script is the other half: it takes the token from the log and
completes the challenge, exactly as clicking the link would.

It deliberately offers no "just mark this address verified" shortcut. The whole
value of the check is that somebody had to receive mail at the address, and a
console flag that skips it would quietly become the way accounts get made.

Usage
-----
    docker compose logs api | Select-String 'E-POSTA DOGRULAMA'

    docker compose exec -T api sh -c "cd /app/scripts && python verify_email.py \\
        --token <token>"

    ... --list
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.core.security import as_utc, hash_session_token


def list_pending(connection) -> None:
    rows = connection.execute(
        text(
            """
            select u.email, u.account_kind, v.expires_at, v.created_at
            from control.email_verifications v
            join control.users u on u.id = v.user_id
            where v.consumed_at is null
            order by v.created_at desc
            """
        )
    ).fetchall()

    if not rows:
        print("Bekleyen doğrulama yok.")
        return

    now = datetime.now(timezone.utc)

    print(f"{len(rows)} bekleyen doğrulama:\n")
    for email, kind, expires_at, created_at in rows:
        state = "SURESI DOLMUS" if as_utc(expires_at) <= now else "gecerli"
        print(f"  {email:36} {kind:14} {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", help="the token from the verification link")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.list:
            list_pending(connection)
            return 0

        if not args.token:
            parser.error("gerekli: --token (veya --list)")

        row = connection.execute(
            text(
                """
                select v.id, v.user_id, v.expires_at, v.consumed_at, u.email
                from control.email_verifications v
                join control.users u on u.id = v.user_id
                where v.token_hash = :token_hash
                """
            ),
            {"token_hash": hash_session_token(args.token.strip())},
        ).fetchone()

        if row is None:
            print("Bu token'a karşılık gelen bir doğrulama yok.")
            return 1

        verification_id, user_id, expires_at, consumed_at, email = row

        if consumed_at is not None:
            print(f"Bu doğrulama zaten kullanılmış: {email}")
            return 1

        if as_utc(expires_at) <= datetime.now(timezone.utc):
            print(f"Doğrulama bağlantısının süresi dolmuş: {email}")
            print("Yenisini istemek için: POST /auth/resend-verification")
            return 1

        connection.execute(
            text(
                "update control.email_verifications "
                "set consumed_at = now() where id = :id"
            ),
            {"id": verification_id},
        )
        connection.execute(
            text(
                "update control.users "
                "set email_verified_at = now(), updated_at = now() "
                "where id = :id"
            ),
            {"id": user_id},
        )

        print(f"Doğrulandı: {email}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
