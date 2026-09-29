# Reconciliation policy preview v1

GET `/reconciliation/source-records/{source_record_id}/evaluation`

This read-only Work endpoint evaluates stored candidates. It does not regenerate
candidates, merge entities, create entities, or save/replace decisions. No migration
is required. The decision POST now enforces acceptance checks described below.

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
large margin proves identity. Legacy evidence cannot distinguish every missing
field from a conflicting field; new generation includes explicit field comparisons. Stored candidates are not bound to source or
canonical data versions, and generation can update existing candidate evidence
while retaining older unmatched candidates. Policy v3 checks stored-candidate input freshness as described below. Immutable
evidence history, creator/identifier signals and a labeled pilot dataset remain
prerequisites for automatic acceptance.
The decision POST now blocks automatic acceptance and validates input freshness
for manual Work acceptance. These checks are not user authentication or authorization.

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

## Field evidence v1 / policy v2 (previous release)

Newly generated candidates use `work_fuzzy_title_v3` with the same scoring weights.
`evidence.field_comparisons.language` and `.work_type` retain original and normalized
values and distinguish `match`, `conflict`, `missing_source`, `missing_candidate`,
`missing_both`, and `invalid_value`. A conflict means normalized values differ under
the current raw-data contract; it is not proof of different bibliographic identity.
No language-code aliases or vocabulary mapping are inferred.

Existing boolean match and numeric score fields remain compatible. Existing evidence
is only upgraded when candidate generation is explicitly run, not on evaluation GET.
Legacy evidence is reported as unavailable rather than interpreted as a conflict.
Policy `work_review_v2` reports comparison issues for the top representative candidate;
all group members retain their own evidence. Freshness remains unverified.


## Input freshness v1 / policy v3

New generation uses `work_fuzzy_title_v4` and `work_fields_v2`. It stores SHA-256
fingerprints plus `generated_at` inside the existing evidence JSON; no migration
is needed. Hashes cover the full source raw_data, source ID and record type, and
canonical Work ID, title, original language and work type. JSON key ordering does
not affect hashes; original values are fingerprinted, so even a change erased by
normalization conservatively requires regeneration. Source content_hash is not
trusted as a substitute for hashing actual inputs.

Each ranked member, and each group's highest-scoring representative, exposes:

- `freshness.status = fresh`: stored inputs and method match current values.
- `stale`: source/Work data, canonical identity or matching method changed.
- `unknown`: fingerprints are absent, malformed or from an unsupported version.

The response includes `freshness_counts`, `requires_candidate_regeneration` and
`stored_candidate_inputs_current`. Excluded invalid canonical candidates remain
reported separately and prevent `stored_candidate_inputs_current` from being true.
The regeneration flag concerns stale/unknown stored inputs, not missing/cyclic
canonical entities that may need a separate integrity repair.

Evaluation remains read-only, with automatic acceptance disabled. Rankings and
margins still reflect STORED scores, including stale or unknown candidates; read
freshness before interpreting them. Candidates that no longer meet retrieval
criteria are preserved and flagged stale rather than silently deleted.

Freshness is a comparison at read time, not a signed audit trail, a guarantee
against concurrent changes, or a guarantee that retrieval covers newly added
Works. It does not cover creator/identifier data not yet used by this scorer.
Generation still replaces evidence on existing candidates; immutable decision and
candidate history remains a separate future task.


## Acceptance guard

POST `/reconciliation/source-records/{source_record_id}/decision` now enforces:

- `accepted` + `automatic`: HTTP 409, `automatic_acceptance_not_calibrated`.
- Manual Work acceptance requires a resolvable canonical Work and fresh evidence.
- Stale/unknown evidence: HTTP 409, `candidate_evidence_requires_regeneration`,
  with freshness details. Regenerate evidence and review before submitting again.
- Cycles/missing canonical Works: HTTP 409 with a specific integrity reason.
- Accepted decisions for other record types: HTTP 400 until their validation exists.
- Existing decisions still return HTTP 409; foreign candidates still return 400.
- Rejected, unresolved and new_entity decision validation is unchanged.

A manual reviewer may accept fresh evidence containing a field conflict. This is a
human judgment, not an automatic score threshold. No real records are accepted by
installation; no migration is needed. Tests exercise writes only in isolated SQLite.
The guard checks current values before insertion; it is not a concurrency lock,
immutable evidence snapshot, or authenticated reviewer identity. Decision history
and concurrency-safe evidence persistence remain future work.
