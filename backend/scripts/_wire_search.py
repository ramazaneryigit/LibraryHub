"""Replace the /search candidate query with a lookup in the derived index.

The endpoint's contract does not change: same parameters, same response shape,
same truncation signal. Only where the candidate work ids come from changes --
from a twenty-condition join to one indexed lookup.
"""

import pathlib

PATH = pathlib.Path("backend/app/api/v1/routes/search.py")

text = PATH.read_text(encoding="utf-8")
lines = text.splitlines()

# Keep everything up to and including the empty-query guard; replace the rest of
# `search()`.
cut = next(
    index
    for index, line in enumerate(lines)
    if line.strip() == "probe = q.strip()"
)

BODY = '''    probe = q.strip()

    # Candidates come from the derived index, not from a twenty-condition join.
    #
    # That join walked works, agents, nomens, identifiers, subjects, expressions,
    # manifestations, publishers and copies in one statement and matched each
    # with its own `ILIKE` -- measured at 944 ms at the top of §15.2, and growing
    # with every field anybody thought to search.
    #
    # `search_documents` holds one normalized body per entity plus the works a
    # match on it resolves to, so an author-name match finds the person's document
    # and resolves to their works without this query naming the author at all.
    #
    # The index is not a new source of truth. It is built from these same tables,
    # `reindex` rebuilds it from scratch, and `run_scale_checks.py` asserts the
    # two agree -- so a wrong index is a failed check rather than a wrong answer
    # nobody can trace.
    #
    # Matching is on the normalized body, which is why `Ayse` finds `Ayşe`: the
    # same normalization the previous query was already applying to names.
    candidate_ids = search_index.search(db, probe, limit=limit)

    results = []
    seen_work_ids = set()

    for work_id in candidate_ids:
        work_detail = build_work_detail(
            work_entity_id=work_id,
            db=db,
        )

        if work_detail is None:
            continue

        canonical_work_entity_id = work_detail["entity_id"]

        if canonical_work_entity_id in seen_work_ids:
            continue

        seen_work_ids.add(canonical_work_entity_id)
        results.append(work_detail)

    return {
        "query": q,
        "count": len(results),
        "limit": limit,
        # The index caps at `limit` before duplicates are collapsed, so a full
        # page is the honest signal that more may exist. Real pagination needs
        # the Search Plane (docs/architecture-v2.md §9); until then the client
        # is told the result set was cut rather than being left to assume it
        # saw everything.
        "truncated": len(candidate_ids) >= limit,
        "results": results,
    }
'''

# Drop the now-unused import: normalization happens inside the index.
kept = [
    line
    for line in lines[:cut]
    if line.strip() != "from ....core.text import normalize_text"
]

# And bring the index in beside the other service imports.
for index, line in enumerate(kept):
    if line.startswith("from ....services.work_detail import"):
        kept.insert(index, "from ....services import search_index")
        break
else:
    raise SystemExit("could not find the service imports")

PATH.write_text("\n".join(kept) + BODY, encoding="utf-8")

print(f"  kesme noktasi : satir {cut + 1}")
print(f"  yeni satir    : {len(kept) + len(BODY.splitlines())}")
