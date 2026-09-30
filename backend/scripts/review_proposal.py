"""Review and apply tenant change proposals, from a console.

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

Prefer the API
--------------
The same work is available to an administrator over HTTP, at
`/api/v1/admin/proposals`, and there `reviewed_by` comes from an authenticated
session. Here it is a name typed on the command line, which records a claim rather
than an identity -- so this tool is for a machine with the owner credential and no
browser, not for routine review.

The rules themselves live in `app/services/proposal_review.py`, shared with those
endpoints. This file used to carry its own copy of them, and the copy went on
importing a module that had been renamed.

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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine

from app.services.proposal_review import (
    apply_proposal,
    as_changes,
    list_proposals,
    load_proposal,
    record_decision,
)


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

    changes = as_changes(proposal["field_changes"])

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
              f"{as_changes(proposal['applied_fields'])}")


def do_apply(connection, proposal) -> int:
    """Write the whitelisted fields, and say what it refused.

    The rules live in `app.services.proposal_review`, shared with the admin API.
    This function is only the console's way of reporting the outcome.
    """

    result = apply_proposal(connection, proposal)

    if not result.ok:
        print(f"  UYGULANAMADI: {result.reason}")

        if result.dropped:
            print(f"    elenenler: {result.dropped}")

        return 1

    print("  UYGULANDI: paylaşılan kayıt güncellendi.")
    for name, value in result.applied.items():
        print(f"    {name} = {value!r}")

    if result.dropped:
        print(f"  beyaz listede olmadığı için elenenler: {result.dropped}")

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
            rows = list_proposals(
                connection,
                status=args.status,
                limit=None,
            )

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
            proposal = load_proposal(connection, args.show)

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

        proposal = load_proposal(connection, proposal_id)

        if proposal is None:
            print("Öneri bulunamadı.")
            return 1

        if proposal["status"] != "pending":
            print(f"Bu öneri zaten '{proposal['status']}' durumunda.")
            return 1

        show(proposal)

        decision = "accepted" if args.accept else "rejected"

        # Carries the same `status = 'pending'` guard as the admin endpoint, so a
        # decision recorded elsewhere between the read above and here writes
        # nothing rather than overwriting it.
        changed = record_decision(
            connection,
            proposal_id,
            decision,
            args.reviewer,
            args.note,
        )

        if not changed:
            print("\n  KARAR YAZILMADI: öneri bu sırada değişti; yeniden okuyun.")
            return 1

        print(f"\n  KARAR: {decision} ({args.reviewer})")

        if args.reject or not args.apply:
            if args.accept and not args.apply:
                print("  Not: karar kaydedildi, hiçbir şey yazılmadı. "
                      "Uygulamak için --apply ekleyin.")
            return 0

        return do_apply(connection, proposal)


if __name__ == "__main__":
    raise SystemExit(main())
