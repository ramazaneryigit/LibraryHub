"""provenance: who says so

§6 decided that every value has a source. `public.source_systems` was created
empty in Aşama 1 for exactly this and has never held a row, because nothing wrote
assertions yet. This is the table that does.

`tenant.change_proposals` is not replaced. A proposal is a *workflow* -- rationale,
evidence, withdrawal, review; an assertion is *data* -- one field, one value, one
source. The first produces the second.

`source_systems` is seeded now: one row for the platform, one per tenant. A
library asserting something is a source, and a source needs a name before it can
be trusted at a level.

Curators and claimants
----------------------
Two rules, enforced the way this project enforces things -- in the database.

Insert: the `source_system_id` must be the one this session is acting as, so a
participant cannot file a claim in somebody else's name. The session variable is
`libraryhub.source_system_id`, the same mechanism as `libraryhub.tenant_id`.
Recording an assertion on behalf of a source is the owner's privilege, which is
how the platform attributes imported data.

Update: `status` and the review columns may only move when the session is acting
as a curator. A source cannot approve itself.

`principal_kind` widens who can hold an account. The old constraint allowed a
tenant-less account only if it was an `admin`, which is why an academician or a
publisher could not exist. They still cannot do anything until a later step gives
them a workspace, but the identity model no longer forbids them.

Revision ID: a4c7e2b91f38
Revises: f3b8d1e64c72
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a4c7e2b91f38"
down_revision: Union[str, Sequence[str], None] = "f3b8d1e64c72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRINCIPALS = (
    "platform",
    "tenant_staff",
    "academician",
    "publisher",
    "isbn_agency",
    "vendor",
)


def upgrade() -> None:
    # ---------------------------------------------------- paydaş tipleri (F)

    op.execute(
        "alter table control.users "
        "add column if not exists principal_kind text not null "
        "default 'tenant_staff'"
    )

    # Everything that exists today is either staff or the platform. The
    # distinction is already recorded -- a tenant-less account is a platform
    # account -- so the backfill reads it rather than guessing.
    op.execute(
        "update control.users set principal_kind = 'platform' "
        "where tenant_id is null"
    )

    op.execute("alter table control.users drop constraint if exists ck_users_principal_kind")
    op.execute(
        "alter table control.users add constraint ck_users_principal_kind "
        "check (principal_kind in (" + ", ".join(f"'{k}'" for k in PRINCIPALS) + "))"
    )

    # The rule that blocked everyone else. A tenant-less account was permitted
    # only for an administrator; a participant who is not a library -- an
    # academician, a publisher, the ISBN agency -- is tenant-less by nature, and
    # a library's staff are the only ones who must belong to one.
    op.execute("alter table control.users drop constraint if exists ck_users_tenant_required")
    op.execute(
        "alter table control.users add constraint ck_users_tenant_required "
        "check (tenant_id is not null or principal_kind <> 'tenant_staff' "
        "       or role = 'admin')"
    )

    # ---------------------------------------------------- kaynak sistemleri (E)

    # `source_systems` exists from Aşama 1 and is empty. Nothing to alter; its
    # columns already carry what a source needs -- type, trust, licence,
    # attribution.
    op.execute(
        """
        insert into public.source_systems
            (id, code, name, system_type, trust_level, license, attribution,
             base_url, is_active, created_at)
        values
            (gen_random_uuid(), 'platform', 'LibraryHub', 'platform', 100,
             'internal', 'LibraryHub', '', true, now())
        on conflict (code) do nothing
        """
    )

    # One source per library: a library asserting something is a source, and it
    # must be nameable before it can be trusted at a level.
    op.execute(
        """
        insert into public.source_systems
            (id, code, name, system_type, trust_level, license, attribution,
             base_url, is_active, created_at)
        select gen_random_uuid(), 'tenant:' || t.slug, t.display_name, 'tenant',
               80, 'internal', t.display_name, '', true, now()
        from control.tenants t
        on conflict (code) do nothing
        """
    )

    # --------------------------------------------------------- beyanlar (E)

    op.execute(
        """
        create table if not exists public.field_assertions (
            id               uuid primary key,
            entity_id        uuid not null
                             references public.entities(id) on delete cascade,
            entity_type      text not null,
            field            text not null,
            value            jsonb,
            source_system_id uuid not null
                             references public.source_systems(id),
            asserted_by      uuid,
            asserted_at      timestamptz not null default now(),
            status           text not null default 'proposed',
            confidence       real,
            reviewed_by      uuid,
            reviewed_at      timestamptz,
            review_note      text,
            constraint ck_field_assertions_status check (
                status in ('proposed', 'accepted', 'rejected', 'superseded')
            ),
            constraint ck_field_assertions_field check (length(field) between 1 and 120)
        )
        """
    )

    for statement in (
        "create index if not exists ix_field_assertions_entity "
        "on public.field_assertions (entity_id, field, asserted_at desc)",
        "create index if not exists ix_field_assertions_source "
        "on public.field_assertions (source_system_id, status)",
        "create index if not exists ix_field_assertions_open "
        "on public.field_assertions (status, asserted_at desc) "
        "where status = 'proposed'",
    ):
        op.execute(statement)

    # ------------------------------------------------- kapsam, veritabanında (F)

    op.execute(
        """
        create or replace function public.guard_assertion_provenance()
        returns trigger
        language plpgsql
        as $guard$
        declare
            acting_source text;
            acting_curator text;
            is_owner boolean;
        begin
            -- The owner credential is the platform operator: it may attribute a
            -- claim to any source, which is how imported data is recorded.
            select pg_has_role(current_user, 'library', 'member') into is_owner;

            if tg_op = 'INSERT' then
                if is_owner then
                    return new;
                end if;

                acting_source := nullif(
                    current_setting('libraryhub.source_system_id', true), ''
                );

                if acting_source is null then
                    raise exception
                        'no source system bound to this session'
                        using errcode = 'insufficient_privilege';
                end if;

                if new.source_system_id <> acting_source::uuid then
                    raise exception
                        'an assertion may only be filed as its own source'
                        using errcode = 'insufficient_privilege';
                end if;

                return new;
            end if;

            -- UPDATE. A source may not approve itself, and may not edit the
            -- value after the fact -- a claim that changes silently is not a
            -- claim. Status and review columns are the curator's alone.
            if is_owner then
                return new;
            end if;

            acting_curator := nullif(
                current_setting('libraryhub.assertion_curator', true), ''
            );

            if acting_curator = 'on' then
                if new.value is distinct from old.value
                   or new.field is distinct from old.field
                   or new.source_system_id is distinct from old.source_system_id then
                    raise exception
                        'a curator may decide a claim but not rewrite it'
                        using errcode = 'insufficient_privilege';
                end if;

                return new;
            end if;

            -- Not a curator: the value is theirs to correct while it is open,
            -- and the decision is not.
            if new.status is distinct from old.status
               or new.reviewed_by is distinct from old.reviewed_by
               or new.reviewed_at is distinct from old.reviewed_at
               or new.review_note is distinct from old.review_note then
                raise exception
                    'only a curator may decide an assertion'
                    using errcode = 'insufficient_privilege';
            end if;

            if old.status <> 'proposed' then
                raise exception
                    'an assertion that has been decided may not be edited'
                    using errcode = 'insufficient_privilege';
            end if;

            return new;
        end;
        $guard$
        """
    )

    op.execute("drop trigger if exists trg_guard_assertion_provenance on public.field_assertions")
    op.execute(
        "create trigger trg_guard_assertion_provenance "
        "before insert or update on public.field_assertions "
        "for each row execute function public.guard_assertion_provenance()"
    )

    # Grants. The application role files claims and updates its own open ones;
    # the decision path runs with the curator session variable set.
    op.execute(
        "grant select, insert, update on public.field_assertions "
        "to libraryhub_app, libraryhub_global_app"
    )
    op.execute(
        "grant select, insert, update on public.source_systems "
        "to libraryhub_app, libraryhub_global_app"
    )


def downgrade() -> None:
    op.execute("drop trigger if exists trg_guard_assertion_provenance on public.field_assertions")
    op.execute("drop function if exists public.guard_assertion_provenance()")
    op.execute("drop table if exists public.field_assertions")

    # The seeded sources are derived from the tenants and can be rebuilt, but
    # only the two kinds this revision introduced are removed.
    op.execute(
        "delete from public.source_systems "
        "where code = 'platform' or code like 'tenant:%'"
    )

    op.execute("alter table control.users drop constraint if exists ck_users_tenant_required")
    op.execute(
        "alter table control.users add constraint ck_users_tenant_required "
        "check (tenant_id is not null or role = 'admin')"
    )

    op.execute("alter table control.users drop constraint if exists ck_users_principal_kind")
    op.execute("alter table control.users drop column if exists principal_kind")
