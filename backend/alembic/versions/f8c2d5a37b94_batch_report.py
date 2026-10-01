"""a batch keeps the report it produced

`ingestion_batches` records counts -- total, created, unchanged, failed -- and
counts are not a report. "416 failed" is not actionable; "118 had no 245 and 201
had no ISBN" is, and it is the thing a library was shown before handing over its
collection.

Without somewhere to keep it, that detail lives only in the HTTP response. The
operator reads it once, the tab is closed, and the reason a block of records did
not arrive is gone -- which is precisely the situation the report exists to
prevent.

JSON rather than columns: the report is a shape the ingest produces rather than a
schema the database promises, and it will gain fields as the mapping learns. A
column per count would need a migration every time we learn to notice something
new.

Revision ID: f8c2d5a37b94
Revises: e5b1c9f74a82
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f8c2d5a37b94"
down_revision: Union[str, Sequence[str], None] = "e5b1c9f74a82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "alter table public.ingestion_batches "
        "add column if not exists report jsonb"
    )

    # `finished_at` descending is how the list is read, and a catalogue with years
    # of imports behind it should not scan to answer "what did we load recently".
    op.execute(
        "create index if not exists ix_ingestion_batches_recent "
        "on public.ingestion_batches (created_at desc)"
    )


def downgrade() -> None:
    op.execute("drop index if exists public.ix_ingestion_batches_recent")
    op.execute(
        "alter table public.ingestion_batches drop column if exists report"
    )
