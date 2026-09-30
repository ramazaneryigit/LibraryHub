"""Text normalization shared by storage and matching.

Architecture v2 §14 and §15.6. This module is the single source of truth for
how a bibliographic title becomes comparable.

Why it exists as its own module
-------------------------------
Matching used to normalize the two sides differently: `works.canonical_title`
was folded with PostgreSQL `lower()` only, while the incoming record went
through the full normalization below. For Turkish that is systematic damage --
an identical title scored 0.714 instead of 1.000:

    similarity(lower('Suç ve Ceza'), 'suc ve ceza')  =  0.714
    similarity(lower('Suç ve Ceza'), 'suç ve ceza')  =  1.000

With a 0.30 acceptance threshold, short or accent-dense titles could fall below
it and never match at all.

The fix is to normalize once, store the result in `works.normalized_title`, and
compare stored value against normalized probe value. That only works if both
sides use exactly this function, so it lives in one place and is imported by the
ORM event that fills the column, the retrieval query, and the migration that
backfills existing rows.

See docs/architecture-v2.md §14, §15.6.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize_text"]


def normalize_text(value: str | None) -> str | None:
    """Fold a string into its comparable form.

    Applies Unicode case folding, strips combining marks (so `ç` -> `c`),
    replaces punctuation with spaces and collapses runs of whitespace.

    Returns ``None`` when the input is ``None`` or has no normalizable content
    left (for example a title made only of punctuation). Callers must treat
    ``None`` as "not comparable" rather than as an empty string.
    """

    if value is None:
        return None

    normalized = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    normalized = re.sub(
        r"[^\w\s]",
        " ",
        normalized,
        flags=re.UNICODE,
    )

    normalized = " ".join(
        normalized.split()
    )

    return normalized or None
