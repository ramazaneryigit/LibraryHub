"""add works.normalized_title for like-for-like title matching

Why this column exists
----------------------
Candidate retrieval compared two differently normalized strings:

    similarity(lower(works.canonical_title), <fully normalized probe>)

The database side was folded with PostgreSQL ``lower()`` only, while the probe
had been through ``normalize_text`` (casefold + strip combining marks + drop
punctuation). For Turkish this is systematic damage -- measured on an identical
title:

    similarity(lower('Suç ve Ceza'), 'suc ve ceza')  =  0.714
    similarity(lower('Suç ve Ceza'), 'suç ve ceza')  =  1.000

With a 0.30 threshold, 0.286 of similarity lost to accent handling can push a
genuine match below acceptance, worse for short and accent-dense titles.

Storing the normalized form on the row makes both sides identical, and gives
the trigram index something to be built on. The companion change in
`retrieve_work_candidates` adds pg_trgm ``%`` blocking so the index is actually
used: without it every source record full-scans ``works`` -- 823 ms for 200 000
rows. See docs/architecture-v2.md §15.5 and §15.6.

Backfill
--------
The backfill runs the *application* normalizer in Python rather than an SQL
approximation. Re-implementing the folding in SQL would reintroduce precisely
the two-sided mismatch this migration exists to remove.

`works.normalized_title` stays nullable: a title with no normalizable content
(for example only punctuation) normalizes to NULL and is not comparable, which
is the correct answer rather than an empty string that would match nothing
anyway.

Revision ID: f2a5c8e36d74
Revises: e1f4b7d25c63
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a5c8e36d74"
down_revision: Union[str, Sequence[str], None] = "e1f4b7d25c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported inside the function on purpose. Alembic loads every revision
    # module to build the revision map -- `alembic heads` and `alembic history`
    # do this without running env.py -- and env.py is what puts the backend
    # directory on sys.path. A module-level `from app...` import therefore made
    # `alembic heads` fail with ModuleNotFoundError.
    from app.normalization import normalize_text

    op.add_column(
        "works",
        sa.Column(
            "normalized_title",
            sa.String(length=1000),
            nullable=True,
        ),
    )

    op.execute(
        """
        CREATE INDEX ix_works_normalized_title_trgm
        ON works USING gin (normalized_title gin_trgm_ops)
        """
    )

    # Backfill existing rows so they are matchable immediately. Core-level
    # UPDATE does not fire the ORM before_update listener, so the value is
    # written explicitly here.
    bind = op.get_bind()

    rows = bind.execute(
        sa.text("SELECT entity_id, canonical_title FROM works")
    ).fetchall()

    for entity_id, canonical_title in rows:
        bind.execute(
            sa.text(
                "UPDATE works SET normalized_title = :normalized "
                "WHERE entity_id = :entity_id"
            ),
            {
                "normalized": normalize_text(canonical_title),
                "entity_id": entity_id,
            },
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_works_normalized_title_trgm")
    op.drop_column("works", "normalized_title")
