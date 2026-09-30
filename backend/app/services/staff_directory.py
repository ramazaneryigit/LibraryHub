"""Reading and managing institutions and staff accounts.

What the application role may do here, and what it may not
----------------------------------------------------------
`libraryhub_global_app` holds `INSERT, SELECT, UPDATE` on `control.users`, because
a panel that cannot manage staff is not a panel. It holds **`SELECT` only** on
`control.tenants`, so institutions are read here and created by
`scripts/register_domain.py` -- which is not a limitation to work around:
`control.tenants` is what row level security keys every tenant query on, and
letting an application session mint one is a different decision from letting it
manage the people inside one.

The boundary that survives the grant is the guard trigger on `control.users`,
which refuses an application role any write to an administrator account, in either
direction (see `a7c3e9f14d26`). Every refusal is also checked here before the
statement runs, so the caller gets a sentence rather than a plpgsql exception --
but the trigger is the guarantee, not this.

An account created here is unverified
-------------------------------------
The same trigger refuses an application role an account that is already verified.
So the panel can open an account but cannot vouch for its address; the holder goes
through the ordinary verification flow. That is not a gap: `create_user.py` runs
with the owner credential and may do both, and this path deliberately has less
authority than the console it replaces for day-to-day work.

See docs/architecture-v2.md §0.22.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.sql import TextClause
from sqlalchemy.types import Uuid

from ..core.security import hash_password

__all__ = [
    "AccountRefused",
    "ROLES",
    "create_user",
    "get_tenant",
    "get_user",
    "list_tenants",
    "list_users",
    "revoke_sessions",
    "set_password",
    "update_user",
]


ROLES = ("admin", "librarian", "viewer")

# Roles the application may assign. `admin` is absent on purpose and the database
# enforces the same thing; see the module docstring.
ASSIGNABLE_ROLES = ("librarian", "viewer")


USER_COLUMNS = (
    "u.id, u.tenant_id, u.email, u.display_name, u.role, u.account_kind, "
    "u.email_verified_at, u.is_active, u.created_at, u.updated_at"
)


class AccountRefused(Exception):
    """A write the rules do not allow.

    Raised before the statement runs so the caller can answer with a sentence.
    The trigger remains the guarantee: this is the explanation, not the boundary.

    Carries the status the API should answer with, because the two cases are not
    the same thing: "you may not touch that account" is a 403, and "that address
    is already taken" is a 409.
    """

    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


def _as_uuid(value: Any) -> Any:
    """A `uuid.UUID`, from whatever the caller or the driver had.

    Raw SQL through `text()` has no result processor, so an id read back from a row
    is a UUID on PostgreSQL and the stored `CHAR(32)` on SQLite.
    """

    if value is None or isinstance(value, uuid.UUID):
        return value

    return uuid.UUID(str(value))


def _typed(sql: str, *identifiers: str) -> TextClause:
    statement = text(sql)

    if identifiers:
        statement = statement.bindparams(
            *(bindparam(name, type_=Uuid) for name in identifiers)
        )

    return statement


USER_SELECT = (
    f"select {USER_COLUMNS}, t.display_name as tenant_name, t.slug as tenant_slug "
    "from control.users u "
    "left join control.tenants t on t.id = u.tenant_id"
)


# ---------------------------------------------------------------- institutions


def list_tenants(executor) -> list[Mapping]:
    """Every institution, with how many accounts it has."""

    return (
        executor.execute(
            text(
                "select t.id, t.slug, t.display_name, t.created_at, "
                "(select count(*) from control.users u where u.tenant_id = t.id) "
                "as staff_count "
                "from control.tenants t "
                "order by t.display_name"
            )
        )
        .mappings()
        .all()
    )


def get_tenant(executor, tenant_id) -> Mapping | None:
    return (
        executor.execute(
            _typed(
                "select t.id, t.slug, t.display_name, t.created_at, "
                "(select count(*) from control.users u where u.tenant_id = t.id) "
                "as staff_count "
                "from control.tenants t where t.id = :id",
                "id",
            ),
            {"id": _as_uuid(tenant_id)},
        )
        .mappings()
        .first()
    )


# ---------------------------------------------------------------------- staff


def list_users(
    executor,
    tenant_id=None,
    role: str | None = None,
    include_platform: bool = True,
    limit: int = 200,
) -> list[Mapping]:
    query = USER_SELECT
    params: dict = {"limit": limit}
    clauses = []
    typed: list = []

    if tenant_id is not None:
        clauses.append("u.tenant_id = :tenant_id")
        params["tenant_id"] = _as_uuid(tenant_id)
        typed.append("tenant_id")
    elif not include_platform:
        clauses.append("u.tenant_id is not null")

    if role is not None:
        clauses.append("u.role = :role")
        params["role"] = role

    if clauses:
        query += " where " + " and ".join(clauses)

    query += " order by u.tenant_id nulls first, u.email limit :limit"

    return executor.execute(_typed(query, *typed), params).mappings().all()


def get_user(executor, user_id) -> Mapping | None:
    return (
        executor.execute(
            _typed(f"{USER_SELECT} where u.id = :id", "id"),
            {"id": _as_uuid(user_id)},
        )
        .mappings()
        .first()
    )


def _assert_touchable(existing: Mapping) -> None:
    """Refuse to change an administrator account.

    Checked before the statement so the caller gets a sentence. It is the same
    rule the trigger enforces, and the trigger is what makes it true.
    """

    if existing["role"] == "admin":
        raise AccountRefused(
            "Yönetici hesapları uygulama üzerinden değiştirilemez. "
            "Bunun için sahip kimlik bilgisiyle create_user.py kullanılmalı."
        )


def create_user(
    executor,
    *,
    tenant_id,
    email: str,
    display_name: str,
    role: str = "librarian",
    password: str,
    account_kind: str | None = None,
) -> Mapping:
    email = email.strip().lower()

    if role not in ASSIGNABLE_ROLES:
        raise AccountRefused(
            f"Uygulama üzerinden yalnızca {', '.join(ASSIGNABLE_ROLES)} rolü "
            f"verilebilir; '{role}' için sahip kimlik bilgisi gerekir."
        )

    existing = executor.execute(
        text("select id from control.users where email = :email"),
        {"email": email},
    ).scalar()

    if existing is not None:
        raise AccountRefused(f"'{email}' zaten kayıtlı.", status_code=409)

    # The account kind is derived from the domain, never taken from the client --
    # the same rule self-registration follows.
    if account_kind is None:
        from ..email_domains import classify_email

        detected, _ = classify_email(email)
        account_kind = detected or "institutional"

    user_id = uuid.uuid4()

    executor.execute(
        _typed(
            "insert into control.users "
            "(id, tenant_id, email, display_name, password_hash, role, "
            " account_kind, email_verified_at, is_active, created_at, updated_at) "
            "values (:id, :tenant_id, :email, :display_name, :password_hash, "
            "        :role, :account_kind, null, true, "
            "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            "id",
            "tenant_id",
        ),
        {
            "id": user_id,
            "tenant_id": _as_uuid(tenant_id),
            "email": email,
            "display_name": display_name,
            "password_hash": hash_password(password),
            "role": role,
            "account_kind": account_kind,
        },
    )

    return get_user(executor, user_id)


def update_user(
    executor,
    user_id,
    *,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> Mapping:
    existing = get_user(executor, user_id)

    if existing is None:
        raise AccountRefused("Hesap bulunamadı.", status_code=404)

    _assert_touchable(existing)

    if role is not None and role not in ASSIGNABLE_ROLES:
        raise AccountRefused(
            f"Uygulama üzerinden yalnızca {', '.join(ASSIGNABLE_ROLES)} rolü "
            f"verilebilir; '{role}' için sahip kimlik bilgisi gerekir."
        )

    assignments = {}
    typed = []

    if display_name is not None:
        assignments["display_name"] = display_name

    if role is not None:
        assignments["role"] = role

    if is_active is not None:
        assignments["is_active"] = is_active

    if not assignments:
        return existing

    rendered = ", ".join(f"{name} = :{name}" for name in assignments)

    executor.execute(
        _typed(
            f"update control.users set {rendered}, "
            "updated_at = CURRENT_TIMESTAMP where id = :id",
            "id",
        ),
        {**assignments, "id": _as_uuid(user_id)},
    )

    # Deactivating an account without ending its sessions leaves whoever holds one
    # logged in until it expires, which is the opposite of what was asked for.
    if is_active is False:
        revoke_sessions(executor, user_id)

    return get_user(executor, user_id)


def set_password(executor, user_id, password: str) -> Mapping:
    existing = get_user(executor, user_id)

    if existing is None:
        raise AccountRefused("Hesap bulunamadı.", status_code=404)

    _assert_touchable(existing)

    executor.execute(
        _typed(
            "update control.users set password_hash = :password_hash, "
            "updated_at = CURRENT_TIMESTAMP where id = :id",
            "id",
        ),
        {"password_hash": hash_password(password), "id": _as_uuid(user_id)},
    )

    revoked = revoke_sessions(executor, user_id)

    user = get_user(executor, user_id)

    return {"user": user, "revoked_sessions": revoked}


def revoke_sessions(executor, user_id) -> int:
    """End every live session for an account.

    A password change that leaves the old sessions running has not locked anybody
    out -- the holder of the old session is still in.
    """

    result = executor.execute(
        _typed(
            "update control.sessions set revoked_at = CURRENT_TIMESTAMP "
            "where user_id = :id and revoked_at is null",
            "id",
        ),
        {"id": _as_uuid(user_id)},
    )

    return result.rowcount
