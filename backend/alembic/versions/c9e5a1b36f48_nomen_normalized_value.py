"""add a comparable form of a name

§14 and §15.6, the second half. `works.normalized_title` was the first: the
stored side was being folded with PostgreSQL `lower()` while the probe side went
through the full `normalize_text`, and for Turkish that is systematic damage. An
identical title scored 0.714 instead of 1.000 against a 0.30 threshold, so a
short, accent-dense title could fall below it and never match at all.

Names have the same problem and no column to solve it with. `nomens` is what
search and blocking match people and concepts on, and every comparison derived
its key on the fly.

Why not a trigger
-----------------
The obvious move is a trigger, and it is the wrong one here. PostgreSQL has no
`unaccent` in this image, and `normalize_text` is not `lower()` plus a translate
table -- it is NFKD, then casefold, then combining-mark removal, then punctuation
to spaces. Writing that again in plpgsql would be a second implementation of one
decision, free to disagree with the first exactly where it matters most: Turkish
`İ`, `ı`, and the dotted/dotless pair that `casefold` and `lower` already treat
differently.

So this follows the precedent that was measured: derived in Python, at the moment
the row is written, by the ORM event in `app/db/models/identity.py`. Every write
path today goes through it.

What keeps it honest
--------------------
An event listener only covers writes that go through the ORM. `run_scale_checks.py`
therefore asserts that no row has a value and no normalized form -- the drift this
design would produce if somebody later wrote the table in raw SQL, caught on the
next run rather than by a reader finding that one name will not match.

Revision ID: c9e5a1b36f48
Revises: b8d4f0a25e37
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9e5a1b36f48"
down_revision: Union[str, Sequence[str], None] = "b8d4f0a25e37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "nomens",
        sa.Column("normalized_value", sa.String(length=1000), nullable=True),
    )

    # Backfilled from Python rather than in SQL, and for the same reason the
    # column is not a trigger: the whole point is that the stored form and the
    # probe form come from one function. A SQL backfill would reintroduce the
    # two-sided mismatch this column exists to remove.
    from app.core.text import normalize_text

    connection = op.get_bind()

    rows = connection.execute(
        sa.text("select id, value from public.nomens")
    ).fetchall()

    for row in rows:
        connection.execute(
            sa.text(
                "update public.nomens set normalized_value = :normalized "
                "where id = :id"
            ),
            {"id": row.id, "normalized": normalize_text(row.value)},
        )

    # GIN trigram, the same shape as the one on works.normalized_title, and for
    # the same reason: blocking and matching ask `%` and `similarity()` questions
    # of this column and nothing else.
    op.execute(
        "create index ix_nomens_normalized_value_trgm "
        "on public.nomens using gin (normalized_value gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("drop index if exists public.ix_nomens_normalized_value_trgm")
    op.drop_column("nomens", "normalized_value")
