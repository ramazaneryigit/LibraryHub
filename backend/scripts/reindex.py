"""Build, feed or inspect the derived search index.

The index is never the source of truth (§9.3): everything here can be deleted and
rebuilt from PostgreSQL, and `--rebuild` is the operation that proves it. Run with
the owner credential, like the other administrative scripts.

Usage
-----
    ... python reindex.py --stats
    ... python reindex.py --consume          # drain the outbox into the index
    ... python reindex.py --rebuild          # drop everything and rebuild
    ... python reindex.py --query "Dostoyevski"
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.services.search_index import consume, reindex, search, stats


def show_stats(connection) -> None:
    summary = stats(connection)

    print(f"  belge          : {summary['documents']}")
    print(f"  esere ulasan   : {summary['reachable']}")
    print(f"  son indeksleme : {summary['indexed_at']}")
    print(f"  bekleyen olay  : {summary['pending_events']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--consume", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=500)

    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.stats:
            show_stats(connection)
            return 0

        if args.consume:
            result = consume(connection, limit=args.limit)
            print(
                f"  tuketilen olay : {result['events']}\n"
                f"  yazilan belge  : {result['documents']}"
            )
            show_stats(connection)
            return 0

        if args.rebuild:
            written = reindex(connection)
            print(f"  yeniden kurulan belge: {written}")
            show_stats(connection)
            return 0

        if args.query:
            works = search(connection, args.query, limit=args.limit)

            print(f"  '{args.query}' -> {len(works)} eser")

            for work_id in works[:20]:
                title = connection.execute(
                    text(
                        "select canonical_title from public.works "
                        "where entity_id = :id"
                    ),
                    {"id": work_id},
                ).scalar()

                print(f"    {title}  [{str(work_id)[:8]}]")

            return 0

        parser.error("bir işlem seçin: --stats, --consume, --rebuild, --query")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
