"""add the transactional outbox

Why this table, now
-------------------
docs/architecture-v2.md §9.2. PostgreSQL stays the source of truth and the search
engine comes later, but the thing that makes it *possible* to add one is a
single table written inside the same transaction as the change it describes. The
alternative -- deciding later that the platform is event-driven -- means going
back over every write path, and there are more of them every phase.

So this is the cheap end of that decision: one table, one partial index, no
operational work.

How the events are written
--------------------------
By trigger, not by the application. A write path that has to remember to append
an event is a write path that will eventually forget, and the failure is silent:
the data changes and the index quietly disagrees with it. `public.emit_outbox_event`
is attached `FOR EACH ROW` to every table whose changes a search index cares
about, and `TG_ARGV` carries the two things a generic function cannot know:

    TG_ARGV[0]  the column holding the aggregate id
    TG_ARGV[1]  'tenant_id' for a tenant-plane table, otherwise absent

The payload records the operation, and on an UPDATE the columns that actually
moved (`to_jsonb(new) - to_jsonb(old)`, which is exactly that set). An indexer
that only knows *that* a row changed has to re-read it; one that knows what moved
can decide whether it needs to.

Deviating from §9.2 in one place
--------------------------------
The section's DDL says `id uuid primary key default uuid7()`. There is no
`uuid7()` in PostgreSQL 16, and the identity strategy's implementation lives in
Python (D4) -- adding a second one in plpgsql would be two implementations of one
decision, free to drift. The column therefore takes `gen_random_uuid()`, and
event order is carried by `occurred_at` instead. That costs nothing real: an
indexer re-reads the current row, so the order two events about the same
aggregate arrive in does not change the answer. If order ever does matter, a
sequence column is the honest way to record it, not the shape of the id.

Revision ID: b8d4f0a25e37
Revises: a7c3e9f14d26
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b8d4f0a25e37"
down_revision: Union[str, Sequence[str], None] = "a7c3e9f14d26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = """
create table if not exists public.outbox_events (
    id             uuid primary key default gen_random_uuid(),
    aggregate_type text not null,
    aggregate_id   uuid not null,
    event_type     text not null,
    payload        jsonb not null default '{}'::jsonb,
    tenant_id      uuid,
    occurred_at    timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int not null default 0,
    last_error     text
)
"""

INDEX = """
create index if not exists ix_outbox_unpublished
    on public.outbox_events (occurred_at)
    where published_at is null
"""

FUNCTION = """
create or replace function public.emit_outbox_event()
returns trigger
language plpgsql
as $function$
declare
    aggregate uuid;
    tenant    uuid;
    body      jsonb;
begin
    -- The aggregate id comes from whichever column the trigger was told about.
    -- Not every table here is keyed on `entity_id`: identifiers and nomens have
    -- their own, and the relation tables have a composite key with no single id
    -- to point at, so they name their left-hand side instead.
    execute format('select ($1).%I', tg_argv[0])
        into aggregate
        using case when tg_op = 'DELETE' then old else new end;

    if array_length(tg_argv, 1) >= 2 and tg_argv[1] is not null then
        execute format('select ($1).%I', tg_argv[1])
            into tenant
            using case when tg_op = 'DELETE' then old else new end;
    end if;

    body := case tg_op
        when 'INSERT' then jsonb_build_object('op', 'INSERT')
        when 'DELETE' then jsonb_build_object('op', 'DELETE')
        else jsonb_build_object(
            'op', 'UPDATE',
            -- The columns whose value actually changed. `jsonb - jsonb` reads
            -- like it would do this and does not exist; subtracting the old
            -- *keys* would drop unchanged ones too and overstate the change. So
            -- the comparison is explicit.
            'changed', (
                select coalesce(jsonb_object_agg(n.key, n.value), '{}'::jsonb)
                from jsonb_each(to_jsonb(new)) as n
                where to_jsonb(old) -> n.key is distinct from n.value
            )
        )
    end;

    insert into public.outbox_events
        (aggregate_type, aggregate_id, event_type, payload, tenant_id)
    values
        (tg_table_name, aggregate, tg_op, body, tenant);

    return case when tg_op = 'DELETE' then old else new end;
end;
$function$
"""


# (schema, table, id column, tenant column or None)
COVERED = (
    # The bibliographic records themselves.
    ("public", "works", "entity_id", None),
    ("public", "expressions", "entity_id", None),
    ("public", "manifestations", "entity_id", None),
    ("public", "persons", "entity_id", None),
    ("public", "collective_agents", "entity_id", None),
    ("public", "concepts", "entity_id", None),
    ("public", "places", "entity_id", None),
    ("public", "time_spans", "entity_id", None),
    ("public", "classification_nodes", "entity_id", None),
    # Their labels and identifiers: what a search actually matches on.
    ("public", "identifiers", "id", None),
    ("public", "nomens", "id", None),
    # The shape of the graph between them.
    ("public", "entity_relation", "id", None),
    ("public", "entity_merges", "id", None),
    # Controlled vocabulary: a classification's scheme name is part of what a
    # reader sees on a record, and which work carries which class is part of the
    # record.
    ("public", "vocabulary_schemes", "id", None),
    ("public", "vocabulary_scheme_editions", "id", None),
    ("public", "work_classifications", "id", None),
    ("public", "work_expression", "work_entity_id", None),
    ("public", "expression_manifestation", "expression_entity_id", None),
    ("public", "work_agent_relation", "work_entity_id", None),
    ("public", "expression_agent_relation", "expression_entity_id", None),
    (
        "public",
        "manifestation_agent_relation",
        "manifestation_entity_id",
        None,
    ),
    # Availability, which the public search result shows.
    ("tenant", "holdings", "id", "tenant_id"),
    ("tenant", "items", "id", "tenant_id"),
    ("tenant", "item_identifiers", "id", "tenant_id"),
)


def _trigger_name(table: str) -> str:
    return f"trg_{table}_outbox"


def _arguments(id_column: str, tenant_column) -> str:
    if tenant_column:
        return f"'{id_column}', '{tenant_column}'"

    return f"'{id_column}'"


def upgrade() -> None:
    op.execute(TABLE)
    op.execute(INDEX)
    op.execute(FUNCTION)

    for schema, table, id_column, tenant_column in COVERED:
        op.execute(
            f"drop trigger if exists {_trigger_name(table)} "
            f"on {schema}.{table}"
        )
        op.execute(
            f"create trigger {_trigger_name(table)} "
            f"after insert or update or delete on {schema}.{table} "
            "for each row execute function public.emit_outbox_event("
            f"{_arguments(id_column, tenant_column)})"
        )


def downgrade() -> None:
    for schema, table, _id_column, _tenant_column in COVERED:
        op.execute(
            f"drop trigger if exists {_trigger_name(table)} "
            f"on {schema}.{table}"
        )

    op.execute("drop function if exists public.emit_outbox_event()")
    op.execute("drop table if exists public.outbox_events")
