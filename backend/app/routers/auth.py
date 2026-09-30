"""Login, logout and "who am I".

Login is the only endpoint in the application that is not tenant-scoped, and it
is the one that establishes the tenant for everything else: the account carries
`tenant_id`, so the client never has to say which library it is acting for.

See docs/architecture-v2.md §0.13.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_TTL_HOURS,
    VERIFICATION_TTL_HOURS,
    as_utc,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from ..control_models import (
    EmailVerification,
    Organization,
    OrganizationDomain,
    Tenant,
    User,
    UserSession,
)
from ..db import get_db
from ..dependencies import current_session, current_user
from ..email_domains import classify_email, domain_of
from ..ids import uuid7


logger = logging.getLogger("libraryhub.auth")


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


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=2, max_length=300)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


def _deliver_verification(email: str, token: str, expires_at: datetime) -> None:
    """Hand the verification link to the person who registered.

    There is no mail sender wired up yet, so the link goes to the application
    log -- which is what a development mailer does, and what
    `scripts/verify_email.py` reads to complete a challenge from the console.

    It is written here rather than returned in the HTTP response on purpose:
    handing the token back to whoever made the request would defeat the check it
    is meant to perform. This function is the single place that changes when a
    real sender exists.
    """

    logger.warning(
        "E-POSTA DOGRULAMA | %s | /auth/verify-email?token=%s | son gecerlilik %s",
        email,
        token,
        expires_at.isoformat(),
    )


def _issue_verification(db: Session, user: User) -> tuple[str, datetime]:
    token = new_session_token()

    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=VERIFICATION_TTL_HOURS
    )

    db.add(
        EmailVerification(
            id=uuid7(),
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )

    return token, expires_at


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Self-registration for a librarian, an academic or an organization contact.

    The account is created immediately but cannot be used until the address has
    been shown to receive mail. Nothing here trusts the caller with a decision
    that matters: the account kind comes from the domain, the tenant comes from
    the organization that domain belongs to, and the role is fixed.
    """

    email = payload.email.strip().lower()

    account_kind, refusal = classify_email(email)

    if account_kind is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=refusal,
        )

    domain = domain_of(email)

    mapping = db.scalar(
        select(OrganizationDomain).where(
            OrganizationDomain.domain == domain
        )
    )

    if mapping is None or mapping.verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"'{domain}' alan adı sistemde bir kuruluşa tanımlı değil. "
                "Kurumunuzun önce sisteme alınması gerekiyor."
            ),
        )

    organization = db.get(Organization, mapping.organization_id)

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alan adının bağlı olduğu kuruluş bulunamadı.",
        )

    existing = db.scalar(select(User).where(User.email == email))

    if existing is not None and existing.email_verified_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu adresle doğrulanmış bir hesap zaten var.",
        )

    if existing is not None:
        # Still pending, so this is the same person retrying or fixing a
        # mistyped detail. Replacing is safe -- an unverified row cannot be
        # logged into, so nothing is taken from anybody -- and it stops an
        # abandoned registration from holding the address hostage.
        db.delete(existing)
        db.flush()

    user = User(
        id=uuid7(),
        tenant_id=organization.tenant_id,
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role="librarian",
        account_kind=account_kind,
        is_active=True,
    )

    db.add(user)
    db.flush()

    token, expires_at = _issue_verification(db, user)
    db.commit()

    _deliver_verification(email, token, expires_at)

    return {
        "status": "verification_sent",
        "email": email,
        "account_kind": account_kind,
        "organization": organization.name,
        "expires_at": expires_at.isoformat(),
    }


@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    verification = db.scalar(
        select(EmailVerification).where(
            EmailVerification.token_hash
            == hash_session_token(payload.token)
        )
    )

    if verification is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doğrulama bağlantısı geçersiz.",
        )

    if verification.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu doğrulama bağlantısı zaten kullanılmış.",
        )

    if as_utc(verification.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doğrulama bağlantısının süresi dolmuş.",
        )

    user = db.get(User, verification.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doğrulama bağlantısı geçersiz.",
        )

    now = datetime.now(timezone.utc)

    verification.consumed_at = now
    user.email_verified_at = now

    db.commit()

    return {
        "status": "verified",
        "email": user.email,
        "account_kind": user.account_kind,
    }


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    payload: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()

    user = db.scalar(select(User).where(User.email == email))

    # One answer whatever happened. Whether an address is registered, and whether
    # it is still unverified, is not something an anonymous caller gets to learn.
    if user is not None and user.email_verified_at is None:
        now = datetime.now(timezone.utc)

        # Outstanding challenges are consumed first so that an older link cannot
        # be replayed after a newer one has been issued.
        db.execute(
            update(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        token, expires_at = _issue_verification(db, user)
        db.commit()

        _deliver_verification(email, token, expires_at)

    return {"status": "verification_sent"}


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

    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "E-posta adresi henüz doğrulanmamış. Doğrulama bağlantısını "
                "kullanın ya da /auth/resend-verification ile yenisini isteyin."
            ),
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
