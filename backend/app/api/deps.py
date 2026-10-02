"""Request-scoped authentication and tenant context.

These are the two dependencies every protected endpoint is built from:

* `current_user` resolves a bearer token to an active staff account, or 401.
* `tenant_db` yields a session already bound to that user's tenant.

`tenant_db` is the important one. It does not filter by tenant in the query --
it binds `libraryhub.tenant_id` and lets the row level security policies on
`tenant.*` do the filtering inside the database. That distinction is the whole
point of OD13: a `WHERE tenant_id = ...` that a future developer forgets is a
data leak, whereas a policy that is always on is not.

See docs/architecture-v2.md §5.2 and §0.13.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import as_utc, hash_session_token
from ..db.models import User, UserSession
from ..db import OwnerSessionLocal, get_db, tenant_session

__all__ = ["current_session", "current_user", "export_db", "require_role", "tenant_db"]


_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def current_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserSession:
    """Resolve the bearer token to a live session.

    The token is looked up by hash, so the value itself is never stored and a
    read of `control.sessions` yields nothing usable.
    """

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header with a bearer token is required",
            headers=_UNAUTHORIZED_HEADERS,
        )

    token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is empty",
            headers=_UNAUTHORIZED_HEADERS,
        )

    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if as_utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
            headers=_UNAUTHORIZED_HEADERS,
        )

    return session


def current_user(
    session: UserSession = Depends(current_session),
    db: Session = Depends(get_db),
) -> User:
    """The authenticated staff account behind the request."""

    user = db.get(User, session.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session refers to a user that no longer exists",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )

    return user


def require_role(*allowed: str):
    """Dependency factory: allow only the listed roles.

    Deliberately small. Roles exist so that a reader cannot write; anything
    finer belongs with the authorization work of a later phase.
    """

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{user.role}' is not allowed here; "
                    f"requires one of: {', '.join(sorted(allowed))}"
                ),
            )

        return user

    return dependency


# The two tiers the global plane is guarded with.
#
# Creating something on the shared plane -- a work nobody has catalogued yet, a
# person, a concept -- is ordinary cataloguing and needs a member of staff.
# Changing an *identity* -- merging two persons, deciding a reconciliation
# candidate, deleting a mapping, loading a batch -- cannot be undone by editing a
# row afterwards, and needs an administrator.
#
# Reads are untouched: they are public by design, and `viewer` exists to say that
# an account may read without writing.
require_staff = require_role("admin", "librarian")
require_admin = require_role("admin")


def tenant_db(user: User = Depends(current_user)):
    """A session scoped to the caller's tenant, enforced by the database.

    Read the module docstring before adding a `WHERE tenant_id = ...` to a
    query that uses this: the filter is already there, in the policy, and adding
    a second one in application code only creates the illusion that the
    application is what protects the data.

    A platform administrator has no tenant (see `User`), and is refused rather
    than bound to one. Picking a tenant for them -- any tenant -- would be the
    whole vulnerability: this is the one place where the value that scopes every
    tenant query comes from, and it must come from the account or not at all.
    """

    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This account is not attached to a library. The tenant plane "
                "answers for one institution at a time; a platform "
                "administrator curates the shared record instead."
            ),
        )

    with tenant_session(user.tenant_id) as db:
        yield db


def owner_db(user: User = Depends(require_admin)):
    """An owner-credential session, for reading across every tenant.

    `tenant.*` is protected by row level security keyed on `libraryhub.tenant_id`,
    and the application role is subject to it -- which is the point. A reviewer
    has to see the proposals every institution has raised at once, and there is no
    single tenant to bind, so under the application role the policies would
    correctly show nothing at all.

    That makes this the most powerful session in the application, and it is
    reachable only by an administrator: the chain starts at `require_admin`, so a
    librarian's request never gets a connection. Admin routes only.
    """

    db = OwnerSessionLocal()

    try:
        yield db
    finally:
        db.close()


def export_db(user: User = Depends(current_user)):
    """The session an export runs on, chosen by who is asking.

    A platform account exports any library and needs the owner credential, because
    no single tenant can be bound and under the application role the policies would
    correctly show nothing.

    Library staff export their own, and for them the tenant session is the right
    answer rather than the weak one: the policies scope it, so a librarian cannot
    reach another library's holdings whether or not a check in the route remembers
    to say so. Widening `owner_db` to librarians would have handed out the most
    powerful session in the application to save writing five lines here.
    """

    if user.principal_kind == "platform":
        db = OwnerSessionLocal()

        try:
            yield db
        finally:
            db.close()

        return

    if user.tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="This account is not bound to a library",
        )

    with tenant_session(user.tenant_id) as db:
        yield db
