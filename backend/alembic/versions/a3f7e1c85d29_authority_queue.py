"""authority candidates: the queue that weak evidence goes into

`authority.suggest` refuses to merge on a spelling resemblance, which is correct
and leaves a question: where does the resemblance go? Without somewhere, the
choice is between merging wrongly and ignoring the match, and ignoring it means
the catalogue quietly accumulates the forty-people problem.

So weak candidates are *recorded* rather than acted on. Nothing changes in the
catalogue; a row appears saying "these two look alike, and here is why", and a
person decides. The queue is the mechanism that lets the rule be strict without
being useless.

Strong evidence is deliberately absent. `suggest` marks it `decides`, and the
ingest acts on it immediately -- an ORCID match does not need a human, and sending
it to a queue would make the queue's arrival meaningless.

The unique constraint is on the pair and the status, so re-running an import does
not produce the same suggestion twice. That matters because re-running is normal:
a library sends a monthly file and most of it is records it already sent.

Revision ID: a3f7e1c85d29
Revises: f8c2d5a37b94
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a3f7e1c85d29"
down_revision: Union[str, Sequence[str], None] = "f8c2d5a37b94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists public.authority_candidates (
            id                 uuid primary key,
            entity_type        text not null,
            incoming_name      text not null,
            incoming_key       text,
            candidate_entity_id uuid not null
                                references public.entities(id) on delete cascade,
            candidate_name     text not null,
            score               real not null,
            strength            text not null default 'weak',
            reason              text not null,
            source_system_id    uuid references public.source_systems(id),
            status              text not null default 'open',
            created_at          timestamptz not null default now(),
            reviewed_by         uuid,
            reviewed_at         timestamptz,
            review_note         text,
            constraint ck_authority_candidates_status check (
                status in ('open', 'merged', 'kept_separate', 'dismissed')
            ),
            -- Strong evidence never lands here; if it did, the queue would stop
            -- meaning "a person is needed".
            constraint ck_authority_candidates_weak check (strength = 'weak')
        )
        """
    )

    # One open suggestion per pair. Re-running an import is normal and must not
    # fill the queue with the same question again.
    op.execute(
        "create unique index if not exists uq_authority_candidates_open "
        "on public.authority_candidates (lower(incoming_name), candidate_entity_id) "
        "where status = 'open'"
    )

    op.execute(
        "create index if not exists ix_authority_candidates_open "
        "on public.authority_candidates (status, score desc) "
        "where status = 'open'"
    )

    op.execute(
        "grant select, insert, update on public.authority_candidates "
        "to libraryhub_app, libraryhub_global_app"
    )


def downgrade() -> None:
    op.execute("drop table if exists public.authority_candidates")
