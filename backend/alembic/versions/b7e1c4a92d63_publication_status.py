"""publication status: a record can exist before the book does

The ISBN agency's whole contribution is the *not yet printed* work, and until now
a manifestation could only describe something that already exists. `publication_date`
is a date; it cannot say "announced" or "in press", and a catalogue that cannot say
that either hides the record or lies about it.

The default is `published`, which is right for every row that exists: all of them
describe books that are on a shelf somewhere. The migration therefore adds a
column and writes no data, and a row that has always meant "published" still does.

The status is not a workflow engine. It is the smallest thing that lets a librarian
answer "is this available to order" without reading a free-text note, and it is
deliberately a single column rather than a history table -- who changed it and when
is already answered by the outbox and by `field_assertions`.

Revision ID: b7e1c4a92d63
Revises: a4c7e2b91f38
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b7e1c4a92d63"
down_revision: Union[str, Sequence[str], None] = "a4c7e2b91f38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUSES = ("announced", "in_press", "published", "out_of_print", "cancelled")


def upgrade() -> None:
    op.execute(
        "alter table public.manifestations "
        "add column if not exists publication_status text not null "
        "default 'published'"
    )

    op.execute(
        "alter table public.manifestations "
        "drop constraint if exists ck_manifestations_publication_status"
    )

    op.execute(
        "alter table public.manifestations "
        "add constraint ck_manifestations_publication_status "
        "check (publication_status in ("
        + ", ".join(f"'{status}'" for status in STATUSES)
        + "))"
    )

    # The question a union catalogue is asked is "what is coming that we could
    # order", and it is asked across every library at once. A partial index keeps
    # that scan proportional to the answer rather than to the catalogue.
    op.execute(
        "create index if not exists ix_manifestations_not_yet_published "
        "on public.manifestations (publication_status, publication_date) "
        "where publication_status in ('announced', 'in_press')"
    )


def downgrade() -> None:
    op.execute("drop index if exists public.ix_manifestations_not_yet_published")
    op.execute(
        "alter table public.manifestations "
        "drop constraint if exists ck_manifestations_publication_status"
    )
    op.execute(
        "alter table public.manifestations "
        "drop column if exists publication_status"
    )
