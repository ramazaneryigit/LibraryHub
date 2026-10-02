"""Role-Based Access Control (RBAC) services.

Roller ve izinler yönetimi. Platform otorite mimarisi için:
- Platform yönetici: her şey
- Kiracı personeli: kendi kiracı düzlemi
- Paydaşlar (akademisyen, yayınevi, ajans, satıcı): farklı kapsamlar
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import Role, Permission, UserRole
from ..core.ids import uuid7

__all__ = [
    "create_role",
    "assign_role",
    "revoke_role",
    "user_has_permission",
    "user_permissions",
    "bootstrap_permissions",
]


# Standart izinler — global, tüm kiracılar için aynı
STANDARD_PERMISSIONS = [
    ("create_work", "Eser oluştur"),
    ("edit_work", "Eser düzenle"),
    ("create_person", "Kişi oluştur"),
    ("create_concept", "Kavram oluştur"),
    ("approve_assertion", "Beyan onayla (küratör)"),
    ("merge_persons", "Kişileri birleştir"),
    ("create_holding", "Nüsha kaydı oluştur"),
    ("edit_holding", "Nüsha kaydı düzenle"),
    ("view_proposals", "Önerileri görüntüle"),
    ("approve_proposal", "Öneri onayla"),
]


def bootstrap_permissions(db: Session) -> None:
    """Standart izinleri veritabanına ekle (idempotent)."""

    for code, label in STANDARD_PERMISSIONS:
        existing = db.scalar(
            select(Permission).where(Permission.code == code)
        )
        if not existing:
            perm = Permission(
                id=uuid7(),
                code=code,
                label=label,
            )
            db.add(perm)
    
    db.commit()


def create_role(
    db: Session,
    tenant_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> Role:
    """Kiracı içinde bir rol oluştur."""

    role = Role(
        id=uuid7(),
        tenant_id=tenant_id,
        name=name,
        description=description,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def assign_role(
    db: Session,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    assigned_by_user_id: uuid.UUID | None = None,
) -> UserRole:
    """Kullanıcıya bir rol atanmış olarak işaretle."""

    # Zaten atanmışsa yok say
    existing = db.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
    )
    if existing:
        return existing

    user_role = UserRole(
        id=uuid7(),
        user_id=user_id,
        role_id=role_id,
        assigned_by_user_id=assigned_by_user_id,
    )
    db.add(user_role)
    db.commit()
    db.refresh(user_role)
    return user_role


def revoke_role(
    db: Session,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
) -> int:
    """Kullanıcıdan bir rol kaldır."""

    result = db.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
    )
    db.commit()
    return result.rowcount


def user_permissions(
    db: Session,
    user_id: uuid.UUID,
) -> list[str]:
    """Kullanıcının sahip olduğu tüm izinlerin listesi."""

    permissions = db.scalars(
        select(Permission.code).distinct().where(
            Permission.id.in_(
                select(Role.id).where(
                    Role.id.in_(
                        select(UserRole.role_id).where(UserRole.user_id == user_id)
                    )
                )
            )
        )
    ).all()
    
    return list(permissions)


def user_has_permission(
    db: Session,
    user_id: uuid.UUID,
    permission_code: str,
) -> bool:
    """Kullanıcının belirli bir izni olup olmadığını kontrol et."""

    has_it = db.scalar(
        select(Permission).where(
            Permission.code == permission_code,
            Permission.id.in_(
                select(Role.id).where(
                    Role.id.in_(
                        select(UserRole.role_id).where(UserRole.user_id == user_id)
                    )
                )
            ),
        ).exists().correlate(None)
    )
    
    return bool(has_it)
