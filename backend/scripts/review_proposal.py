"""Review and apply tenant change proposals.

The two halves of one conversation. A tenant cannot write the global plane --
PostgreSQL refuses it -- so an institution that finds a wrong publication date
says so with a proposal. This is where somebody reads it and decides.

Why accepting and applying are separate
---------------------------------------
`--accept` records a decision and writes nothing. `--apply` is what actually
writes, and it only writes fields on a whitelist. Collapsing the two would mean a
reviewer who believes a correction is right in principle also silently approves
whatever shape the JSON happens to have, and "the database accepted this value"
is not the same claim as "this is a valid publication date".

The whitelist is deliberately short. A tenant may propose a change to shared
bibliographic description; they may not propose their way into the identity
registry, into `entity_merges`, or into anything that would let a correction
become a merge.

There is no administrator identity yet
--------------------------------------
`reviewed_by` records a name given on the command line, not an authenticated
account. That is honest about where this stands: the panel phase needs a real
administrator identity, and until it exists this is a privileged console tool
like `create_user.py` and `register_domain.py`, run with the owner credential.

Usage
-----
    ... python review_proposal.py --list
    ... python review_proposal.py --list --status pending
    ... python review_proposal.py --show <id>

    ... python review_proposal.py --accept <id> --reviewer "R. Eryigit" \\
            --note "Kaynak dogrulandi" --apply
    ... python review_proposal.py --reject <id> --reviewer "..." --note "..."
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text


# Which fields a proposal is allowed to actually move, per entity kind. The table
# and column names come from here and never from the proposal, so a crafted
# `field` cannot reach a column this list does not name.
#
# `timestamp` is stated per table rather than assumed: none of these three has an
# `updated_at`, and the first version of this script wrote `updated_at = now()`
# for all of them and failed on every apply.
APPLICABLE_FIELDS = {
    "work": {
        "table": "public.works",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "canonical_title",
            "original_title",
            "original_language",
            "description",
        ),
    },
    "expression": {
        "table": "public.expressions",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "language",
            "expression_form",
            "description",
        ),
    },
    "manifestation": {
        "table": "public.manifestations",
        "key": "entity_id",
        "timestamp": None,
        "fields": (
            "publication_statement",
            "publication_date",
            "edition_statement",
            "carrier_type",
            "extent",
            "notes",
        ),
    },
}


PROPOSAL_SELECT = (
    "id, tenant_id, submitted_by_email, change_type, target_entity_type, "
    "target_entity_id, field_changes, rationale, evidence, status, reviewed_by, "
    "reviewed_at, review_note, applied_at, applied_fields, created_at"
)


def as_list(value) -> list:
    """`field_changes` comes back as a list, or as text on a driver without a
    JSON loader. Both are accepted so the tool does not depend on which."""

    if value is None:
        return []

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []

    return value


def load(connection, proposal_id: str):
    return connection.execute(
        text(
            f"SELECT {PROPOSAL_SELECT}, "
            "(SELECT t.display_name FROM control.tenants t "
            " WHERE t.id = p.tenant_id) AS tenant_name "
            "FROM tenant.change_proposals p WHERE p.id = :id"
        ),
        {"id": proposal_id},
    ).mappings().first()


def show(proposal) -> None:
    print(f"  oneri      : {proposal['id']}")
    print(f"  kurum      : {proposal['tenant_name']} ({proposal['tenant_id']})")
    print(f"  gonderen   : {proposal['submitted_by_email']}")
    print(f"  tur        : {proposal['change_type']}")
    print(f"  hedef      : {proposal['target_entity_type']} "
          f"{proposal['target_entity_id']}")
    print(f"  durum      : {proposal['status']}")
    print(f"  gerekce    : {proposal['rationale']}")
    print(f"  kaynak     : {proposal['evidence']}")

    changes = as_list(proposal["field_changes"])

    print(f"  degisiklik : {len(changes)}")

    for change in changes:
        print(
            f"    {change.get('field')}: "
            f"{change.get('current')!r} -> {change.get('proposed')!r}"
        )

    if proposal["reviewed_at"]:
        print(f"  inceleyen  : {proposal['reviewed_by']} "
              f"({proposal['reviewed_at']}) {proposal['review_note'] or ''}")

    if proposal["applied_at"]:
        print(f"  uygulandi  : {proposal['applied_at']} "
              f"{as_list(proposal['applied_fields'])}")


def do_apply(connection, proposal) -> int:
    """Write the whitelisted fields, and say what it refused."""

    target_id = proposal["target_entity_id"]

    if target_id is None:
        print("  UYGULANAMADI: ekleme onerileri bu araçla uygulanmaz; "
              "kaydı bir yönetici oluşturmalı.")
        return 1

    entity_type = connection.execute(
        text("SELECT entity_type FROM entities WHERE id = :id"),
        {"id": target_id},
    ).scalar()

    if entity_type is None:
        print(f"  UYGULANAMADI: {target_id} diye bir entity yok.")
        return 1

    kind = entity_type.lower()
    allowed = APPLICABLE_FIELDS.get(kind)

    changes = as_list(proposal["field_changes"])

    if allowed is None:
        print(f"  UYGULANAMADI: '{kind}' tipi için uygulanabilir alan tanımlı "
              "değil.")
        return 1

    # A proposal carries what the tenant *believes* the target is; the registry
    # is what it actually is. A disagreement is worth stopping for.
    claimed = (proposal["target_entity_type"] or "").lower()

    if claimed and claimed != kind:
        print(f"  UYGULANAMADI: öneri '{claimed}' diyor, kayıt '{kind}'.")
        return 1

    assignments = {}
    dropped = []

    for change in changes:
        field = change.get("field")

        if field in allowed["fields"]:
            assignments[field] = change.get("proposed")
        else:
            dropped.append(field)

    if not assignments:
        print("  UYGULANAMADI: beyaz listedeki hiçbir alan önerilmemiş.")
        print(f"    elenenler: {dropped}")
        return 1

    # `public.works.normalized_title` is maintained by an ORM event listener, and
    # raw SQL does not trigger it. Leaving it stale would silently break matching
    # for exactly the record somebody just corrected -- and it is computed from
    # the column being changed, so it cannot be forgotten here.
    if allowed["table"] == "public.works" and "canonical_title" in assignments:
        from app.normalization import normalize_text

        assignments["normalized_title"] = normalize_text(
            assignments["canonical_title"] or ""
        )

    rendered = ", ".join(f"{name} = :{name}" for name in assignments)

    if allowed["timestamp"]:
        rendered += f", {allowed['timestamp']} = now()"

    connection.execute(
        text(
            f"UPDATE {allowed['table']} SET {rendered} "
            f"WHERE {allowed['key']} = :target_id"
        ),
        {**assignments, "target_id": target_id},
    )

    connection.execute(
        text(
            "UPDATE tenant.change_proposals "
            "SET status = 'applied', applied_at = now(), "
            "applied_fields = :applied, updated_at = now() "
            "WHERE id = :id"
        ),
        {
            "id": proposal["id"],
            "applied": json.dumps(sorted(assignments)),
        },
    )

    print(f"  UYGULANDI: {allowed['table']} güncellendi.")
    for name, value in assignments.items():
        print(f"    {name} = {value!r}")

    if dropped:
        print(f"  beyaz listede olmadığı için elenenler: {dropped}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--status", default="pending")
    parser.add_argument("--show")
    parser.add_argument("--accept")
    parser.add_argument("--reject")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewer", help="who is deciding")
    parser.add_argument("--note")

    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.list:
            query = (
                f"SELECT {PROPOSAL_SELECT}, "
                "(SELECT t.display_name FROM control.tenants t "
                " WHERE t.id = p.tenant_id) AS tenant_name "
                "FROM tenant.change_proposals p"
            )
            params: dict = {}

            if args.status != "all":
                query += " WHERE status = :status"
                params["status"] = args.status

            query += " ORDER BY created_at"

            rows = connection.execute(text(query), params).mappings().all()

            if not rows:
                print(f"'{args.status}' durumunda öneri yok.")
                return 0

            print(f"{len(rows)} öneri:\n")
            for proposal in rows:
                print(
                    f"  {proposal['id']}  {proposal['status']:10} "
                    f"{proposal['change_type']:10} "
                    f"{(proposal['tenant_name'] or '')[:28]:28} "
                    f"{(proposal['rationale'] or '')[:50]}"
                )
            return 0

        if args.show:
            proposal = load(connection, args.show)

            if proposal is None:
                print("Öneri bulunamadı.")
                return 1

            show(proposal)
            return 0

        proposal_id = args.accept or args.reject

        if not proposal_id:
            parser.error("bir işlem seçin: --list, --show, --accept, --reject")

        if not args.reviewer:
            parser.error("--reviewer gerekli: kararı kimin verdiği kaydedilmeli")

        proposal = load(connection, proposal_id)

        if proposal is None:
            print("Öneri bulunamadı.")
            return 1

        if proposal["status"] != "pending":
            print(f"Bu öneri zaten '{proposal['status']}' durumunda.")
            return 1

        show(proposal)

        decision = "accepted" if args.accept else "rejected"

        connection.execute(
            text(
                "UPDATE tenant.change_proposals "
                "SET status = :status, reviewed_by = :reviewer, "
                "reviewed_at = now(), review_note = :note, updated_at = now() "
                "WHERE id = :id"
            ),
            {
                "id": proposal_id,
                "status": decision,
                "reviewer": args.reviewer,
                "note": args.note,
            },
        )

        print(f"\n  KARAR: {decision} ({args.reviewer})")

        if args.reject or not args.apply:
            if args.accept and not args.apply:
                print("  Not: karar kaydedildi, hiçbir şey yazılmadı. "
                      "Uygulamak için --apply ekleyin.")
            return 0

        return do_apply(connection, proposal)


if __name__ == "__main__":
    raise SystemExit(main())
