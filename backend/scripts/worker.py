"""The outbox consumer, running on its own.

Until now the index was fed by somebody remembering to run `reindex.py --consume`.
That is not a delay, it is an uncertainty: after a library adds a holding, nobody
knows when the catalogue will show it, because the answer is "when a person runs a
script". This is the process that removes the question.

Why a separate process and not a thread in the API
-------------------------------------------------
The API runs with several workers. A thread in each of them would consume the same
events concurrently, and while `consume` is written so duplicates are survivable,
"survivable" is not the standard -- the outbox is what the search index is built
from, and it should be drained by one thing.

It is deliberately dull: read, index, mark published, sleep, repeat. Everything
interesting is in `search_index.consume`, which the checks and `reindex.py` call
too, so the worker cannot drift from them.

Lag is reported, not assumed
----------------------------
Each pass logs how old the oldest unpublished event is. That number is the honest
answer to "is the catalogue current", and it belongs in a log line rather than in
somebody's belief about how fast the machine is.
"""

from __future__ import annotations

import json
import os
import uuid
import signal
from urllib.request import Request, urlopen
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import Uuid

from app.services.search_index import consume, stats


# How long to wait when there is nothing to do. Short enough that a library's
# change is visible before anyone has finished looking at the screen; long enough
# that an idle catalogue costs nothing.
IDLE_SECONDS = float(os.environ.get("LIBRARYHUB_WORKER_INTERVAL", "5"))

# How many events one pass takes. A backlog is drained in batches rather than in
# one transaction that grows until it fails.
BATCH = int(os.environ.get("LIBRARYHUB_WORKER_BATCH", "1000"))
SEMANTIC_URL = os.environ.get("SEMANTIC_SEARCH_URL")

_running = True


def _stop(signum, frame):  # noqa: ARG001 - the signature is fixed by signal
    global _running

    _running = False

    print(f"  signal {signum}: bitiriliyor, elimdeki isi bitirip cikiyorum", flush=True)


def lag(connection) -> float | None:
    """Seconds since the oldest unpublished event, or None when there is none.

    This is the number that answers "is the index current", and it is the reading
    a monitoring system should alert on rather than on whether the worker is alive
    -- a running worker that is an hour behind is worse than a stopped one,
    because it looks healthy.
    """

    seconds = connection.execute(
        text(
            "select extract(epoch from (now() - min(occurred_at))) "
            "from public.outbox_events where published_at is null"
        )
    ).scalar()

    return float(seconds) if seconds is not None else None


def semantic_request(path: str, payload: dict | None = None) -> dict:
    request = Request(
        f"{SEMANTIC_URL.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def semantic_document(row) -> dict:
    return {
        "entity_id": str(row["entity_id"]),
        "entity_type": row["entity_type"],
        "label": row["label"],
        "body": row["body"],
        "work_ids": [str(work_id) for work_id in row["work_ids"]],
    }


def initialize_semantic_index(engine) -> None:
    status = semantic_request("/status")
    if status["ready"]:
        print(f"  semantik indeks hazır: {status['point_count']} belge", flush=True)
        return

    semantic_request("/reset", {})
    after = None
    indexed = 0
    with engine.connect() as connection:
        while True:
            rows = connection.execute(
                text(
                    "select entity_id, entity_type, label, body, work_ids "
                    "from public.search_documents "
                    "where cast(:after as uuid) is null "
                    "   or entity_id > cast(:after as uuid) "
                    "order by entity_id limit :batch"
                ),
                {"after": after, "batch": BATCH},
            ).mappings().all()
            if not rows:
                break
            for start in range(0, len(rows), 256):
                semantic_request(
                    "/sync",
                    {
                        "documents": [
                            semantic_document(row)
                            for row in rows[start : start + 256]
                        ]
                    },
                )
            indexed += len(rows)
            after = str(rows[-1]["entity_id"])

    semantic_request("/ready", {})
    print(f"  semantik indeks eşitlendi: {indexed} belge", flush=True)


def sync_semantic_changes(connection, document_ids: list[str]) -> None:
    if not document_ids:
        return

    ids = [uuid.UUID(entity_id) for entity_id in document_ids]
    statement = text(
        "select entity_id, entity_type, label, body, work_ids "
        "from public.search_documents where entity_id = any(:ids)"
    ).bindparams(bindparam("ids", type_=ARRAY(Uuid)))
    rows = connection.execute(statement, {"ids": ids}).mappings().all()
    existing_ids = {str(row["entity_id"]) for row in rows}
    for start in range(0, len(rows), 256):
        semantic_request(
            "/sync",
            {
                "documents": [
                    semantic_document(row)
                    for row in rows[start : start + 256]
                ]
            },
        )

    deleted_ids = [entity_id for entity_id in document_ids if entity_id not in existing_ids]
    for start in range(0, len(deleted_ids), 1000):
        semantic_request(
            "/sync",
            {"delete_ids": deleted_ids[start : start + 1000]},
        )


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

    print(
        f"  isci basladi: aralik {IDLE_SECONDS}s, parti {BATCH}",
        flush=True,
    )

    if SEMANTIC_URL:
        while _running:
            try:
                initialize_semantic_index(engine)
                break
            except Exception as error:  # noqa: BLE001 - keep retrying until local index is reachable
                print(f"  semantik indeks baslatilamadi: {type(error).__name__}: {error}", flush=True)
                time.sleep(IDLE_SECONDS)

    idle_passes = 0

    while _running:
        try:
            with engine.begin() as connection:
                result = consume(connection, limit=BATCH)
                if SEMANTIC_URL and result["events"]:
                    sync_semantic_changes(connection, result["document_ids"])
                current_lag = lag(connection)

            if result["events"]:
                idle_passes = 0

                lag_note = (
                    f"; gecikme {current_lag:.1f}s"
                    if current_lag is not None
                    else ""
                )

                print(
                    f"  {result['events']} olay -> {result['documents']} belge"
                    f"{lag_note}",
                    flush=True,
                )

            else:
                idle_passes += 1

                # Once a minute when idle: enough to show the worker is alive
                # without printing the same line every five seconds.
                if idle_passes % 12 == 0:
                    with engine.connect() as connection:
                        summary = stats(connection)

                    print(
                        f"  bekleyen olay yok; belge {summary['documents']}",
                        flush=True,
                    )

        except Exception as error:  # noqa: BLE001 - a worker that dies on one bad
            # row is a worker that stops indexing until somebody notices, which is
            # the failure this process exists to prevent.
            print(f"  HATA: {type(error).__name__}: {error}", flush=True)

        # Sleep in short slices so a signal is acted on promptly rather than after
        # the full interval.
        waited = 0.0

        while _running and waited < IDLE_SECONDS:
            time.sleep(0.25)
            waited += 0.25

    print("  isci durdu", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
