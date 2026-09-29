# Reconciliation policy preview v1

GET `/reconciliation/source-records/{source_record_id}/evaluation`

This read-only Work endpoint evaluates stored candidates. It does not regenerate
candidates, merge entities, create entities, or save/replace decisions. No migration
is required. Existing endpoints retain their behavior.

- Historical candidate IDs and evidence remain visible under each group's `members`.
- Candidates resolving to the same canonical Work form one ranked group.
- The highest stored score represents the group; scores are never added together.
- Equal scores use UUID ordering for stable display, not semantic preference.
- `score_margin` compares the first two distinct canonical Works; with fewer than
  two groups it is null, not the first score minus zero.
- Cyclic redirects and missing canonical Work subtypes are excluded with reasons.
- The current decision is returned separately and remains authoritative.
- No candidates yields `unresolved`; usable candidates yield `manual_review`.
- `automatic_acceptance_eligible` is always false in this uncalibrated policy.

Scores are ranking signals, not probabilities. The preview does not infer that a
large margin proves identity. Current evidence cannot distinguish every missing
field from a conflicting field. Stored candidates are not bound to source or
canonical data versions, and generation can update existing candidate evidence
while retaining older unmatched candidates. Therefore every response explicitly
reports `candidate_freshness_not_verified`. Versioned evidence, creator/identifier
signals and a labeled pilot dataset are prerequisites for automatic acceptance.
The existing decision POST can still accept caller-supplied automatic decisions;
this preview is not an authorization or enforcement gate for that endpoint.

## Local verification

From `backend`, install `requirements-test.txt` and run:

```sh
python -m unittest discover -s tests -v
```

Tests use a separate in-memory SQLite engine and FastAPI HTTP requests. They do
not test PostgreSQL migrations, concurrency, or the user's running database.

## Windows verification after integrating the branch

From `E:\library-platform`, restart/rebuild the API as appropriate for the Compose
setup, then inspect the controlled fuzzy source record:

```powershell
Invoke-RestMethod 'http://localhost:8010/reconciliation/source-records/bb673bb2-24f2-4870-ba1b-c04dcae1de0c/evaluation' | ConvertTo-Json -Depth 12
```

A single candidate must have a null margin and automatic acceptance disabled.
