"""the derived search index

§9.3 in one sentence: the index is never the source of truth, and it must always
be fully reproducible from PostgreSQL.

Why a table in PostgreSQL and not an engine
-------------------------------------------
§9.1 says the search engine comes later and that the problem today is not the
absence of one. What the index has to prove before an engine is worth adding is
that it can be built, fed incrementally, and thrown away and rebuilt to the same
state. That proof does not need Elasticsearch; it needs a table.

One document per entity, each carrying the works it belongs to
--------------------------------------------------------------
The shape is chosen so the outbox maps onto it one-to-one. An event names a table
and a row; the indexer resolves that row to the *document entity* it affects --
an item belongs to its holding's manifestation, a nomen belongs to the entity it
names -- and rebuilds that one document. No fan-out, no full scan.

`work_ids` is what makes the index usable rather than decorative: a match on a
person's name resolves to the works they wrote without a second traversal, which
is the whole question `/search` asks.

The body
--------
Text is not built here. `normalize_text` is Python (NFKD, casefold, combining
marks, punctuation) and this image has no `unaccent`, so building the body in SQL
would be a second implementation of one decision -- the same reasoning as
`nomens.normalized_value` (§0.27). The indexer composes it in Python through one
function that both the incremental path and `reindex` call, so the two cannot
disagree.

Indexes
-------
Trigram GIN on `body` for matching, GIN on `work_ids` for resolving a match to
works. Both live on the derived table, which is the point: they can be dropped
and rebuilt without touching a single source row.

Revision ID: f3b8d1e64c72
Revises: e2a7c3d58b61
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f3b8d1e64c72"
down_revision: Union[str, Sequence[str], None] = "e2a7c3d58b61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = """
create table if not exists public.search_documents (
    entity_id         uuid primary key,
    entity_type       text not null,
    label             text not null default '',
    body              text not null default '',
    work_ids          uuid[] not null default '{}'::uuid[],
    source_updated_at timestamptz not null default now(),
    indexed_at        timestamptz not null default now()
)
"""

INDEXES = (
    "create index if not exists ix_search_documents_body_trgm "
    "on public.search_documents using gin (body gin_trgm_ops)",
    "create index if not exists ix_search_documents_work_ids "
    "on public.search_documents using gin (work_ids)",
    "create index if not exists ix_search_documents_type "
    "on public.search_documents (entity_type)",
)


def upgrade() -> None:
    op.execute(TABLE)

    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    # The whole table goes. It holds nothing that is not derived from the source
    # tables, which is the property this revision exists to establish: dropping
    # it loses no information, only the time to rebuild it.
    op.execute("drop table if exists public.search_documents")
