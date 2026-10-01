"""a participant who is not a library is not an administrator of one

`role` says what somebody may do *inside* a library -- curate the shared record,
manage staff, edit holdings. A publisher, an academician, the ISBN agency or a
vendor is not inside a library, and none of those permissions mean anything for
them; what they may do follows from `principal_kind`.

Two reasons this is a constraint rather than a convention.

The first is that the account guard refuses an application role any write to an
account with `role = 'admin'`, in either direction, so a participant account
carrying that role cannot even be bound to its own authority record -- which is
exactly what happened when an academician tried to claim an ORCID. Making the
combination impossible removes the collision instead of working around it.

The second is the reason this project gives for everything else: a rule the
database enforces survives a new code path, and one that lives in a script does
not.

The platform keeps `admin`, because a platform account genuinely does administer.

Revision ID: e5b1c9f74a82
Revises: d2a8f4b63e17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e5b1c9f74a82"
down_revision: Union[str, Sequence[str], None] = "d2a8f4b63e17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A default of `viewer` for the four participants, applied now so that any
    # account already carrying the combination is corrected rather than making the
    # constraint fail to install. There is exactly one such account in this
    # database -- the test academician -- and it is a viewer in every way that
    # matters.
    op.execute(
        "update control.users set role = 'viewer' "
        "where principal_kind not in ('tenant_staff', 'platform') "
        "  and role = 'admin'"
    )

    op.execute(
        "alter table control.users "
        "drop constraint if exists ck_users_staff_role_only"
    )

    op.execute(
        "alter table control.users add constraint ck_users_staff_role_only "
        "check (principal_kind in ('tenant_staff', 'platform') or role <> 'admin')"
    )


def downgrade() -> None:
    op.execute(
        "alter table control.users "
        "drop constraint if exists ck_users_staff_role_only"
    )
