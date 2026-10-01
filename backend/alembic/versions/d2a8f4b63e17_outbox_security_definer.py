"""the outbox trigger must write with its own privileges, not the caller's

A tenant write is refused with "permission denied for table outbox_events", and
the reason is structural rather than accidental: every watched table fires
`emit_outbox_event`, the event lands in `public.outbox_events`, and inside a
tenant transaction the current role is `libraryhub_tenant_app` -- which is
deliberately forbidden from writing the global plane. So *every* tenant write was
broken, because every tenant write emits an event.

The two facts are both correct and they simply collide:

  * the tenant role must not write the global plane (that is the isolation), and
  * a change must be recorded when it happens (that is the outbox).

`SECURITY DEFINER` is how PostgreSQL resolves that without weakening either. The
function runs as its owner -- the `library` superuser, which created it -- so the
event is written with the privileges the *function* has, not the ones the caller
has. A tenant still cannot insert into `outbox_events` directly; it can only cause
an event by making a change, which is exactly the distinction we want.

The alternative -- granting the tenant role INSERT on `outbox_events` -- would
have made every tenant able to forge events for changes it never made, and the
outbox is what the search index is built from. `SECURITY DEFINER` keeps the write
on the caller's behalf while keeping the privilege out of the caller's hands.

Revision ID: d2a8f4b63e17
Revises: c9f3a7e15b28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2a8f4b63e17"
down_revision: Union[str, Sequence[str], None] = "c9f3a7e15b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `ALTER FUNCTION ... SECURITY DEFINER` rather than recreating it: the body is
    # the outbox logic and rewriting it here would be a second copy of a decision
    # that must only have one.
    op.execute(
        "alter function public.emit_outbox_event() security definer"
    )

    # The owner must be able to write the event, and it is. The search path is
    # pinned so the function resolves `outbox_events` to the same table no matter
    # who calls it -- a `SECURITY DEFINER` function with a mutable search path is
    # a way to be tricked into writing somewhere else.
    op.execute(
        "alter function public.emit_outbox_event() set search_path = public, pg_temp"
    )


def downgrade() -> None:
    op.execute("alter function public.emit_outbox_event() reset search_path")
    op.execute("alter function public.emit_outbox_event() security invoker")
