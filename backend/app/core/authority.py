"""Deciding when two author names are the same person.

The weakest join in the pipeline, and the one that costs most when it is wrong. A
thousand libraries bring the same author spelled forty ways:

    Dostoyevski, Fyodor · Dostoevsky, Fyodor · Fyodor Dostoyevski · Достоевский, Фёдор

Today `marc_ingest` matches on the exact canonical name, which turned forty
spellings into forty people -- and a union catalogue that invents people is worse
than one that refuses records, because nobody can tell which is which afterwards.

Two kinds of evidence, and they are not equal
---------------------------------------------
**Strong** decides: an ORCID, an ISBN, a set of dates that agree. Two records
carrying the same ORCID *are* the same person, and no name similarity needs to be
consulted.

**Weak** only suggests: a folded surname and a forename initial. `Dostoyevski, F.`
matches both `Fyodor` and `Fyodor Mihayloviç`, and it also matches every other
Dostoyevski with an F.

So this module **never merges on weak evidence** ✗. It produces candidates with a
score and a reason, and something else -- a person, a queue -- decides. Automating
the weak case is how a catalogue ends up attributing one scholar's work to another,
and that error is invisible once it is made.

Turkish
-------
`İ` folds to `i` and `I` to `ı`, not the other way round, and `ş`, `ğ`, `ç`, `ö`,
`ü` fold to their ASCII forms for comparison. Getting this wrong is not cosmetic:
`İnce` and `Ince` are the same author, and a Turkish catalogue where they are not
is a catalogue that has split its own literature.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping

from .orcid import normalize_orcid

__all__ = [
    "Candidate",
    "closeness",
    "fold",
    "match_key",
    "parse_name",
    "similarity",
    "suggest",
]


# Applied before NFKD, because NFKD does not know Turkish: it maps `İ` to `I` plus
# a combining dot, and `ı` stays `ı`. Doing this first is what keeps `İnce` and
# `Ince` together.
TURKISH = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ç": "c", "ç": "c",
    "Ö": "o", "ö": "o",
    "Ü": "u", "ü": "u",
})

# Name particles that are not the surname and should not decide a match:
# `van der Berg`, `bin Ahmed`, `de la Cruz`.
PARTICLES = {
    "van", "von", "der", "den", "de", "la", "le", "el", "al", "bin", "ibn",
    "mac", "mc", "o", "dos", "das", "di", "da",
}

# Used to strip a role or a qualifier that arrives with a name: `Dostoyevski, F.
# (çeviren)` or `Kaya, Bilge, 1970-`.
NOISE = re.compile(r"[,;]?\s*\d{3,4}\s*[-–]\s*\d{0,4}\s*$|\(.*?\)")


@dataclass
class Candidate:
    """Someone who might be the same person, and why we think so."""

    entity_id: str | None
    name: str
    score: float
    strength: str  # 'strong' | 'weak'
    reason: str

    @property
    def decides(self) -> bool:
        """Whether this alone is enough to merge.

        Only strong evidence decides. `suggest` returns weak candidates with
        useful scores so a queue can be ordered, and this property is what stops
        that queue from being automated away.
        """

        return self.strength == "strong"


def fold(text: str | None) -> str:
    """A comparable form of a name.

    Turkish letters first, then NFKD to separate accents, then the combining marks
    removed, then everything that is not a letter or a digit becomes a space.
    Punctuation is not part of a name; `Dostoyevski, F.` and `Dostoyevski F` are
    the same string afterwards.
    """

    if not text:
        return ""

    translated = text.translate(TURKISH)
    decomposed = unicodedata.normalize("NFKD", translated)

    stripped = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    lowered = stripped.casefold()
    spaceless = re.sub(r"[^a-z0-9]+", " ", lowered)

    return " ".join(spaceless.split())


def parse_name(name: str | None) -> tuple[str, list[str]]:
    """Surname and forenames, from either way round a catalogue writes it.

    `Dostoyevski, Fyodor` is the inverted form MARC uses and `Fyodor Dostoyevski`
    is the natural one, and both arrive. Guessing wrong is not fatal here because
    the key is built from both -- but the surname is what matters most, and a
    particle at the front (`van der Berg`) must not become the surname.
    """

    cleaned = NOISE.sub("", name or "").strip()

    if not cleaned:
        return "", []

    if "," in cleaned:
        surname, _, rest = cleaned.partition(",")
        words = fold(surname).split()

        if not words:
            return "", fold(rest).split()

        # A particle is not the deciding part in either form. `van der Berg, Jan`
        # and `Jan van der Berg` must give the same surname, or the two ways a
        # catalogue writes one name become two people.
        index = len(words) - 1

        while index > 0 and words[index] in PARTICLES:
            index -= 1

        return words[index], fold(rest).split()

    words = fold(cleaned).split()

    if not words:
        return "", []

    if len(words) == 1:
        return words[0], []

    # In the natural form the surname is last, unless the last word is a particle,
    # in which case keep walking back.
    index = len(words) - 1

    while index > 0 and words[index] in PARTICLES:
        index -= 1

    return words[index], words[:index]


def match_key(name: str | None) -> str:
    """The weak key: surname plus the first initial of each forename.

    `Dostoyevski, Fyodor` and `Dostoevsky, Fyodor Mihayloviç` both give
    `dostoyevski|f`, which is why this suggests and does not decide.
    """

    surname, forenames = parse_name(name)

    if not surname:
        return ""

    initials = "".join(forename[0] for forename in forenames if forename)

    return f"{surname}|{initials}"


# Words that say what a body is rather than which one it is. Every publisher's
# name contains `Yayınları`, so sharing it is not evidence of anything -- and
# measured on real data it was the strongest thing in the queue: `Türkiye İş
# Bankası Kültür Yayınları` and `TTK Yayınları` scored 0.90 on it and sat at the
# top, above the genuine spelling variants a reviewer was looking for.
#
# Excluded from the token comparison rather than weighted down, because a shared
# generic word is not weak evidence, it is no evidence.
GENERIC = {
    "yayinlari", "yayincilik", "yayinevi", "yayin", "basimevi", "matbaa",
    "dergi", "dergisi", "kitap", "kitaplari", "kutuphanesi",
    "universitesi", "university", "universite", "enstitusu", "fakultesi",
    "press", "publishing", "publisher", "publishers", "books", "book",
    "inc", "ltd", "llc", "as", "gmbh", "co",
}


def _tokens(value: str | None) -> set:
    """The words of a name that carry identity."""

    words = fold(value).split()

    if not words:
        return set()

    meaningful = {word for word in words if word not in GENERIC}

    # Everything was generic, so nothing is filtered -- otherwise two names would
    # compare as equal for having no tokens at all.
    return meaningful or set(words)


def closeness(left: str | None, right: str | None) -> float:
    """Character-level likeness, for spellings of one name.

    Token overlap cannot see that `dostoevsky` and `dostoyevski` are one surname:
    they share no token at all. Transliteration is exactly where this bites --
    `Dostoevsky` and `Dostoyevski`, `Tolstoy` and `Tolstoi` -- and a union
    catalogue's whole problem is transliterations.

    Still weak evidence. A one-letter difference is also how `Kaya` and `Kaya`
    differ from `Kaya` and `Kaya`, and it is how `Yılmaz` and `Yıldız` are close.
    """

    a = fold(left)
    b = fold(right)

    if not a or not b:
        return 0.0

    return difflib.SequenceMatcher(None, a, b).ratio()


def similarity(left: str | None, right: str | None) -> float:
    """How much two names look alike, from 0 to 1.

    Token overlap rather than edit distance: `Dostoyevski, Fyodor` and `Fyodor
    Dostoyevski` share both tokens and are 1.0, while a character-distance measure
    would call them half different purely because the order changed.
    """

    a = _tokens(left)
    b = _tokens(right)

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def suggest(
    name: str | None,
    existing: Iterable[Mapping],
    *,
    orcid: str | None = None,
    dates: str | None = None,
    threshold: float = 0.5,
) -> list[Candidate]:
    """Everyone who might be this person, best first, each with a reason.

    `existing` is what the catalogue already has: anything with a `name` and an
    optional `entity_id`, `orcid` and `dates`.

    A strong match is returned on its own and `decides` is true, so a caller can
    merge without asking. Weak matches are returned with scores so a queue can be
    ordered, and `decides` is false so a caller that automates them has to do it
    deliberately rather than by accident.
    """

    key = match_key(name)
    candidates = []

    for entry in existing:
        entity_id = entry.get("entity_id")
        other_name = entry.get("name") or ""

        if orcid and entry.get("orcid") and normalize_orcid(orcid) == normalize_orcid(entry["orcid"]):
            candidates.append(
                Candidate(
                    entity_id=str(entity_id) if entity_id else None,
                    name=other_name,
                    score=1.0,
                    strength="strong",
                    reason="ayni ORCID",
                )
            )
            continue

        # Dates agreeing is strong only when both are present. Absent dates are
        # agreement about nothing, which is why the check is on values rather than
        # on absence.
        if dates and entry.get("dates") and fold(dates) == fold(entry["dates"]):
            candidates.append(
                Candidate(
                    entity_id=str(entity_id) if entity_id else None,
                    name=other_name,
                    score=0.98,
                    strength="strong",
                    reason="ayni tarihler",
                )
            )
            continue

        # An identical folded name decides.
        #
        # Two people can share a name, so this is not proof in the abstract -- but
        # it is what the catalogue already keyed on, and treating it as merely
        # similar *regressed*: a publisher that arrived twice, once as `TTK
        # Yayinlari` and once as `TTK Yayınları`, produced a duplicate record and
        # a queue entry saying the duplicate matched at 1.00. Being told that two
        # identical names might be the same is not useful information.
        if fold(name) == fold(other_name):
            candidates.append(
                Candidate(
                    entity_id=str(entity_id) if entity_id else None,
                    name=other_name,
                    score=1.0,
                    strength="strong",
                    reason="ayni ad",
                )
            )
            continue

        score = similarity(name, other_name)

        # The surname at character level, because token overlap cannot see that
        # `dostoevsky` and `dostoyevski` are one name. Scaled rather than taken as
        # equal: a near-miss surname is weaker evidence than a shared token.
        #
        # Skipped when either surname is a generic word. `TTK Yayınları` and
        # `Türkiye İş Bankası Kültür Yayınları` both end in `Yayınları`, so their
        # surnames compare at 1.0 and they scored 0.90 -- the noise fix had to
        # reach here too, or it only fixed half the score.
        left_surname = parse_name(name)[0]
        right_surname = parse_name(other_name)[0]

        surname_score = 0.0

        if left_surname not in GENERIC and right_surname not in GENERIC:
            surname_score = closeness(left_surname, right_surname) * 0.9

        score = max(score, surname_score)

        # The key matching is worth raising, because a shared surname and initial
        # is more than a shared token: `Dostoyevski, F` and `Dostoevsky, Fyodor`
        # share no token at all when the spelling differs.
        same_key = key and key == match_key(other_name)

        if same_key:
            score = max(score, 0.75)

        if score >= threshold:
            candidates.append(
                Candidate(
                    entity_id=str(entity_id) if entity_id else None,
                    name=other_name,
                    score=round(score, 3),
                    strength="weak",
                    reason=(
                        "ayni soyad ve bas harfler"
                        if same_key
                        else "benzer ad"
                    ),
                )
            )

    candidates.sort(key=lambda candidate: -candidate.score)

    return candidates
