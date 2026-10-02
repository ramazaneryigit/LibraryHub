"""restore the authority candidate queue used by imports and curator review

Revision ID: d94c72e10a6b
Revises: 8a4c2f9b1e5d
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d94c72e10a6b"
down_revision: Union[str, Sequence[str], None] = "8a4c2f9b1e5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        create table public.authority_candidates (
            id                  uuid primary key,
            entity_type         text not null,
            incoming_name       text not null,
            incoming_key        text,
            incoming_entity_id  uuid references public.entities(id) on delete cascade,
            candidate_entity_id uuid not null
                                references public.entities(id) on delete cascade,
            candidate_name      text not null,
            score                real not null,
            strength             text not null default 'weak',
            reason               text not null,
            source_system_id     uuid references public.source_systems(id) on delete set null,
            status               text not null default 'open',
            created_at           timestamptz not null default now(),
            reviewed_by          uuid references control.users(id) on delete set null,
            reviewed_at          timestamptz,
            review_note          text,
            constraint ck_authority_candidates_status check (
                status in ('open', 'merged', 'kept_separate', 'dismissed')
            ),
            constraint ck_authority_candidates_weak check (strength = 'weak')
        )
        """
    )

    op.execute(
        "create unique index uq_authority_candidates_open "
        "on public.authority_candidates (lower(incoming_name), candidate_entity_id) "
        "where status = 'open'"
    )
    op.execute(
        "create index ix_authority_candidates_open "
        "on public.authority_candidates (status, score desc) "
        "where status = 'open'"
    )
    op.execute(
        "create index ix_authority_candidates_incoming_entity "
        "on public.authority_candidates (incoming_entity_id)"
    )
    op.execute(
        "grant select, insert, update on public.authority_candidates "
        "to libraryhub_app, libraryhub_global_app"
    )


def downgrade() -> None:
    op.execute("drop table public.authority_candidates")