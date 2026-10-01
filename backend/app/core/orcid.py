"""ORCID iD validation.

An ORCID iD is sixteen digits in four groups: 0000-0002-1825-0097. The last digit
is an ISO 7064 MOD 11-2 check digit, which means a mistyped iD can be refused
before it reaches the database rather than becoming a second record for somebody
who already exists.

That matters more here than it looks. The whole point of binding an account to a
person through ORCID is that ORCID is an authority the person maintains
themselves; if we accept `0000-0002-1825-0098` because it looks right, we have
invented a person, and the union catalogue will show two of them.

Nothing here talks to orcid.org. Validating the shape is free and catches typing;
proving the iD belongs to whoever is signing in needs OAuth, which is a different
piece of work and is not pretended here.
"""

from __future__ import annotations

import re

__all__ = ["format_orcid", "is_valid_orcid", "normalize_orcid"]


DIGITS = re.compile(r"\d{15}[\dX]")


def _check_digit(first_fifteen: str) -> str:
    """ISO 7064 MOD 11-2, which is what ORCID uses."""

    total = 0

    for character in first_fifteen:
        total = (total + int(character)) * 2

    remainder = total % 11
    result = (12 - remainder) % 11

    return "X" if result == 10 else str(result)


def normalize_orcid(value: str | None) -> str | None:
    """The iD in its canonical hyphenated form, or None if it is not an iD.

    Accepts what people actually paste -- with or without hyphens, with a full
    `https://orcid.org/` URL, with `X` in either case -- and returns one spelling.
    Two spellings of one iD would be two people.
    """

    if not value:
        return None

    text = value.strip()

    # A pasted profile URL is the common case, not an edge case.
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break

    text = text.replace(" ", "").replace("-", "").upper()

    if not DIGITS.fullmatch(text):
        return None

    if _check_digit(text[:15]) != text[15]:
        return None

    return f"{text[0:4]}-{text[4:8]}-{text[8:12]}-{text[12:16]}"


def is_valid_orcid(value: str | None) -> bool:
    return normalize_orcid(value) is not None


def format_orcid(value: str | None) -> str | None:
    """Alias kept for call sites that read better as formatting."""

    return normalize_orcid(value)
