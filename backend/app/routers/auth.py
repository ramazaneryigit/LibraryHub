"""Login, logout and "who am I".

Login is the only endpoint in the application that is not tenant-scoped, and it
is the one that establishes the tenant for everything else: the account carries
`tenant_id`, so the client never has to say which library it is acting for.

See docs/architecture-v2.md §0.13.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_TTL_HOURS,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from ..control_models import Tenant, User, UserSession
from ..db import get_db
from ..dependencies import current_session, current_user
from ..ids import uuid7


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """A real hash to verify against when the account does not exist.

    Returning early for an unknown email would make "no such account" measurably
    faster than "wrong password" -- the KDF is ~50 ms -- which is enough to
    enumerate accounts. Verified lazily so importing this module stays cheap.
    """

    global _DUMMY_HASH

    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-password")

    return _DUMMY_HASH


def _user_view(user: User, tenant: Tenant | None) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": str(user.tenant_id),
        "tenant_name": tenant.display_name if tenant else None,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is None:
        verify_password(payload.password, _dummy_hash())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Reached only with a correct password, so saying the account is disabled
    # leaks nothing an attacker did not already have.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )

    token = new_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)

    db.add(
        UserSession(
            id=uuid7(),
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()

    tenant = db.get(Tenant, user.tenant_id)

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "user": _user_view(user, tenant),
    }


@router.post("/logout")
def logout(
    session: UserSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    return {"revoked": True}


@router.get("/me")
def me(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return _user_view(user, db.get(Tenant, user.tenant_id))
