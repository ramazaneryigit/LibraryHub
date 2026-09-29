"""Fingerprint the inputs used by Work scoring, without changing source data."""

import hashlib
import json
import re
from datetime import datetime, timezone

METHOD = "work_fuzzy_title_v4"
FINGERPRINT_VERSION = "work_inputs_v1"


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def input_fingerprints(source, work) -> dict:
    return {
        "version": FINGERPRINT_VERSION,
        "source_hash": _digest({
            "id": str(source.id),
            "record_type": source.record_type,
            "raw_data": source.raw_data,
        }),
        "work_hash": _digest({
            "entity_id": str(work.entity_id),
            "canonical_title": work.canonical_title,
            "original_language": work.original_language,
            "work_type": work.work_type,
        }),
        "canonical_entity_id": str(work.entity_id),
        "method": METHOD,
    }


def capture_inputs(source, work) -> dict:
    return {**input_fingerprints(source, work),
            "generated_at": datetime.now(timezone.utc).isoformat()}


def check_freshness(source, work, candidate) -> dict:
    evidence = candidate.evidence
    stored = evidence.get("input_fingerprints") if isinstance(evidence, dict) else None
    if not isinstance(stored, dict):
        return {"status": "unknown", "reason_codes": ["input_fingerprints_missing"]}
    if stored.get("version") != FINGERPRINT_VERSION:
        return {"status": "unknown", "reason_codes": ["fingerprint_version_unsupported"]}
    if any(not isinstance(stored.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", stored[key])
           for key in ("source_hash", "work_hash")) or not all(
               isinstance(stored.get(key), str) and stored[key]
               for key in ("canonical_entity_id", "method")):
        return {"status": "unknown", "reason_codes": ["input_fingerprints_invalid"]}
    current = input_fingerprints(source, work)
    reasons = []
    for key, reason in (("source_hash", "source_data_changed"),
                        ("work_hash", "work_data_changed"),
                        ("canonical_entity_id", "canonical_identity_changed")):
        if stored[key] != current[key]:
            reasons.append(reason)
    if stored["method"] != METHOD or candidate.method != METHOD:
        reasons.append("matching_method_changed")
    return {"status": "stale" if reasons else "fresh", "reason_codes": reasons}
