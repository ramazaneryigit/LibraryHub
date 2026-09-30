"""Password hashing and session tokens, standard library only.

Why the standard library
------------------------
`requirements.txt` deliberately carries no authentication dependency, and the
two things actually needed are both built in: `hashlib.scrypt` is a memory-hard
KDF present in the running image (verified: ~48 ms at n=2**14), and `secrets` is
the correct source for unguessable tokens. Adding passlib, bcrypt and a JWT
library would be three dependencies for what these two already do.

Why sessions are server-side rows, not signed tokens
----------------------------------------------------
A signed token carries its own validity, so revoking one -- because staff left,
because a laptop was lost -- needs a denylist somewhere anyway. A library system
will need revocation from day one, so the session is a row that can simply be
marked revoked. Only the SHA-256 of the token is stored, so a dump of
`control.sessions` does not hand anyone a usable credential.

See docs/architecture-v2.md §0.13.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

__all__ = [
    "SESSION_TTL_HOURS",
    "VERIFICATION_TTL_HOURS",
    "as_utc",
    "hash_password",
    "hash_session_token",
    "new_session_token",
    "verify_password",
]


# scrypt cost. n=2**14 measured at ~48 ms in the running image: expensive enough
# to make offline guessing costly, fast enough for an interactive login.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_SALT_BYTES = 16

SESSION_TTL_HOURS = 12
VERIFICATION_TTL_HOURS = 24


def as_utc(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC.

    PostgreSQL returns aware datetimes for `timestamptz`; SQLite does not, so a
    comparison against `datetime.now(timezone.utc)` raises TypeError on the test
    engine only. Normalising keeps expiry checks correct on both instead of
    hiding the difference behind a driver-specific assumption.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def hash_password(password: str) -> str:
    """Return a self-describing hash: ``scrypt$n$r$p$salt$hash``.

    Self-describing so that the cost parameters can be raised later without
    invalidating existing passwords: verification reads them back from the
    stored value instead of assuming today's constants.
    """

    if not password:
        raise ValueError("Password must not be empty")

    salt = secrets.token_bytes(_SALT_BYTES)

    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )

    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            salt.hex(),
            derived.hex(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash."""

    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")

        if scheme != "scrypt":
            return False

        expected = bytes.fromhex(hash_hex)

        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )

    except (AttributeError, TypeError, ValueError):
        return False

    return hmac.compare_digest(derived, expected)


def new_session_token() -> str:
    """A fresh bearer token. Returned to the caller exactly once."""

    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """What actually gets stored and looked up."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
