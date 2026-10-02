"""MARC21 to our model: what a record says, and what we could not read.

Pure. A parsed `Record` goes in, a `MappedRecord` comes out, nothing touches a
database. That is deliberate and it is the same reasoning as the parser: this is
where every judgement about a record is made, so it is where a mistake is most
expensive and where being testable on its own matters most.

The problems list is not decoration
-----------------------------------
It is the report promised to a library before they hand over a collection:

    Alınan kayıt    : 42.318
    Eşleşmeyen      :    416
      ├─ 245 boş    :    118
      ├─ 020 ISBN yok:   201
      └─ 852 kod yok :    97

A system that says "42,318 records loaded" proves nothing. One that says which
field failed tells the catalogue what to fix, and tells the library that we are
not going to pretend a half-imported collection is a whole one. So every problem
here is a *named, countable* thing rather than a skip.

What is deliberately unreadable
-------------------------------
`852$b` is an institution code -- `TR-KKU` -- and on its own it is an opaque
string. Without a code list that resolves it, no holding can be created and the
library simply does not appear. That is why `library_code` is carried rather than
interpreted: the mapping says what the record claims, and the code list decides
what it means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Mapping

from .marc import Record

__all__ = [
    "ItemRef",
    "MappedAuthor",
    "MappedRecord",
    "NormalizedCode",
    "map_record",
    "normalize_library_code",
]


# ISBD punctuation is part of the *display* of a MARC field, and MARC carries it
# inside the value: `Suç ve Ceza /` ends with a slash meaning "responsibility
# statement follows", and `1821-1881.` ends with the period that separates areas.
# Both belong to the display and neither belongs to the catalogue, where they
# would put a slash or a full stop inside every title and every date.
#
# A question mark or an exclamation mark is left alone: those are punctuation the
# title actually has, and `Who is Mr. X?` must not lose its shape.
TRAILING_ISBD = re.compile(r"\s*[/:;,=.]\s*$")

# An ISBN arrives with how it is bound: `9789750000011 (pbk.)`. The parenthetical
# is not part of the identifier.
ISBN_QUALIFIER = re.compile(r"\s*\(.*?\)\s*")


@dataclass
class NormalizedCode:
    """A library code as the record writes it, and as we would look it up."""

    raw: str
    normalized: str


@dataclass
class MappedAuthor:
    name: str
    dates: str | None = None
    role: str | None = None
    relator: str | None = None
    main: bool = False


@dataclass
class ItemRef:
    """A copy the record says the library holds."""

    barcode: str | None = None
    shelfmark: str | None = None
    note: str | None = None


@dataclass
class MappedRecord:
    control_number: str | None = None
    title: str | None = None
    subtitle: str | None = None
    original_title: str | None = None
    authors: list[MappedAuthor] = dataclass_field(default_factory=list)
    isbn: list[str] = dataclass_field(default_factory=list)
    issn: list[str] = dataclass_field(default_factory=list)
    language: str | None = None
    # The publication statement as one rendered string -- "İstanbul : Ağaç
    # Yayıncılık, 1993." -- alongside its parts where we have them.
    #
    # We store the statement as a single column and cannot un-render it, so on the
    # way out it is written back whole rather than pretending to know where the
    # place ends and the publisher begins. Splitting it would be guessing.
    publication_statement: str | None = None
    publication_place: str | None = None
    publisher: str | None = None
    publication_date: str | None = None
    edition_statement: str | None = None
    carrier_type: str | None = None
    subjects: list[str] = dataclass_field(default_factory=list)
    call_number: str | None = None
    extent: str | None = None
    notes: str | None = None
    library_code: NormalizedCode | None = None
    items: list[ItemRef] = dataclass_field(default_factory=list)
    problems: list[str] = dataclass_field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Whether there is enough here to make a work.

        A title is the one thing a bibliographic record cannot do without. It
        alone is enough; everything else is enrichment, and a record missing an
        ISBN is still a record.
        """

        return bool(self.title)

    @property
    def gives_a_holding(self) -> bool:
        """Whether this record can place a copy in a library.

        Needs both a library code to resolve and something to hold -- a
        manifestation, which needs a title. Without the code the record is
        bibliographic only: useful, but it puts no book on any shelf.
        """

        return bool(self.title and self.library_code)

    def summary(self) -> str:
        parts = [f"'{self.title or '(baslik yok)'}'"]

        if self.authors:
            parts.append(f"{len(self.authors)} yazar")

        if self.isbn:
            parts.append(f"ISBN {self.isbn[0]}")

        if self.library_code:
            parts.append(f"kutuphane {self.library_code.raw}")

        if self.items:
            parts.append(f"{len(self.items)} nusha")

        return " | ".join(parts)


def normalize_library_code(raw: str) -> str:
    """A library code in the form we would look it up.

    `TR-KKU`, `tr-kku`, `TR KKU` and ` TR-KKU ` are one library. Two spellings
    would be two libraries, and a union catalogue that invents a library is worse
    than one that refuses a record.
    """

    return re.sub(r"[\s_]+", "-", raw.strip().upper())


def _clean(value: str | None) -> str | None:
    if value is None:
        return None

    text = TRAILING_ISBD.sub("", value.strip()).strip()

    return text or None


def _first(record: Record, tag: str, code: str | None = None) -> str | None:
    value = record.value(tag, code)

    return _clean(value) if value is not None else None


def _authors(record: Record) -> list[MappedAuthor]:
    """Main and added entries, in the order the record gives them.

    `100` is the main entry and `700` the added ones, and both are authorship.
    `$e` is the free-text role -- "çeviren", "editör" -- and `$4` the coded
    relator; both are kept because the free text is what a reader sees and the
    code is what a machine can act on.
    """

    authors = []

    for tag, main in (("100", True), ("700", False), ("110", True), ("710", False)):
        for entry in record.everything(tag):
            name = _clean(entry.get("a"))

            if not name:
                continue

            authors.append(
                MappedAuthor(
                    name=name,
                    dates=_clean(entry.get("d")),
                    role=_clean(entry.get("e")),
                    relator=_clean(entry.get("4")),
                    main=main,
                )
            )

    return authors


def _identifiers(record: Record, tag: str) -> list[str]:
    values = []

    for raw in record.values(tag, "a"):
        cleaned = ISBN_QUALIFIER.sub("", raw).strip()

        if cleaned:
            values.append(cleaned)

    return values


def _language(record: Record) -> str | None:
    """`041$a` first, then the fixed field.

    `008` positions 35-37 hold the language when `041` is absent, which is common
    in records from smaller libraries. Reading it costs three characters and saves
    a whole class of record from arriving with no language at all.
    """

    from_041 = _first(record, "041", "a")

    if from_041:
        return from_041

    fixed = record.first("008")

    if fixed and fixed.subfields:
        raw = fixed.subfields[0][1]

        if len(raw) >= 38:
            candidate = raw[35:38].strip()

            if candidate and candidate != "   ":
                return candidate

    return None


def _publication(record: Record) -> tuple[str | None, str | None, str | None]:
    """Place, publisher and date from `264` or the older `260`.

    `264` is the current field and `260` the pre-RDA one; a national catalogue
    receives both and neither is wrong.
    """

    for tag in ("264", "260"):
        entry = record.first(tag)

        if entry is None:
            continue

        return (
            _clean(entry.get("a")),
            _clean(entry.get("b")),
            _clean(entry.get("c")),
        )

    return None, None, None


def _subjects(record: Record) -> list[str]:
    """`650` headings, subdivided.

    `$a` with its `$x` subdivisions joined by a dash is how a subject heading is
    written, and joining them is what makes "Rus edebiyatı - Roman" one heading
    rather than two unrelated words.
    """

    subjects = []

    for entry in record.everything("650"):
        parts = [_clean(entry.get("a"))]
        parts.extend(_clean(value) for value in entry.all("x"))

        joined = " - ".join(part for part in parts if part)

        if joined:
            subjects.append(joined)

    return subjects


def _call_number(record: Record) -> str | None:
    """The shelf address, preferring what the holding itself says.

    `852$h` with `$i` is where *this library* put it, which beats a shared
    classification: the question a reader asks is where it is on the shelf here.
    `082` (Dewey) and `050` (LC) are the fallbacks.
    """

    holding = record.first("852")

    if holding:
        parts = [_clean(holding.get("h")), _clean(holding.get("i"))]

        joined = " ".join(part for part in parts if part)

        if joined:
            return joined

    for tag in ("082", "050"):
        value = _first(record, tag, "a")

        if value:
            return value

    return None


def _items(record: Record) -> list[ItemRef]:
    """Copies, from the holdings fields.

    `876` is the item information field and `$p` its piece designation, which is
    the barcode on the book. `$a` is the library's own item number and is used
    when there is no `$p`. Not every library exports these -- TO-KAT data is
    largely holding-level -- and a record without them still places a book in a
    library, just not on a numbered shelf.
    """

    items = []

    for tag in ("876", "877", "878"):
        for entry in record.everything(tag):
            barcode = _clean(entry.get("p")) or _clean(entry.get("a"))

            if not barcode:
                continue

            items.append(
                ItemRef(
                    barcode=barcode,
                    shelfmark=_clean(entry.get("l")) or _clean(entry.get("h")),
                    note=_clean(entry.get("z")),
                )
            )

    return items


def _library_code(record: Record) -> NormalizedCode | None:
    """`852$b`: the library, as a code.

    Carried unresolved on purpose. What `TR-KKU` means is a fact about a code
    list, not about this record, and guessing at it would create libraries that do
    not exist.
    """

    raw = _first(record, "852", "b")

    if not raw:
        return None

    return NormalizedCode(raw=raw, normalized=normalize_library_code(raw))


def map_record(record: Record) -> MappedRecord:
    """One MARC record, as much of it as we can honestly read."""

    mapped = MappedRecord(
        control_number=_first(record, "001"),
        title=_first(record, "245", "a"),
        subtitle=_first(record, "245", "b"),
        authors=_authors(record),
        isbn=_identifiers(record, "020"),
        issn=_identifiers(record, "022"),
        language=_language(record),
        edition_statement=_first(record, "250", "a"),
        subjects=_subjects(record),
        call_number=_call_number(record),
        library_code=_library_code(record),
        items=_items(record),
    )

    mapped.publication_place, mapped.publisher, mapped.publication_date = (
        _publication(record)
    )

    # `240` is the uniform title -- the original, when the record describes a
    # translation -- and it is a different thing from `245`, which is what the
    # reader sees.
    mapped.original_title = _first(record, "240", "a") or _first(record, "130", "a")

    statement = record.first("260") or record.first("264")

    if statement:
        parts = [
            _clean(statement.get("a")),
            _clean(statement.get("b")),
            _clean(statement.get("c")),
        ]

        joined = " ".join(part for part in parts if part)

        if joined:
            mapped.publication_statement = joined

    # `300` is the physical description -- "135 sayfa : resim ; 18 cm." -- and
    # `504` a bibliography note. Both were unread until a real record from a
    # university library arrived carrying them, and both had columns waiting:
    # `extent` and `notes`.
    extent = record.first("300")

    if extent:
        parts = [
            _clean(extent.get("a")),
            _clean(extent.get("b")),
            _clean(extent.get("c")),
        ]

        joined = " ".join(part for part in parts if part)

        if joined:
            mapped.extent = joined

    notes = []

    for tag in ("504", "500", "502", "505"):
        for entry in record.everything(tag):
            text = _clean(entry.get("a"))

            if text:
                notes.append(text)

    if notes:
        mapped.notes = " | ".join(notes)

    carrier = _first(record, "338", "a") or _first(record, "337", "a")

    if carrier:
        mapped.carrier_type = carrier

    # The problems, named and countable. Each one is a thing somebody could go and
    # fix in the source record, which is what makes this a report rather than a
    # complaint.
    if not mapped.title:
        mapped.problems.append("245$a bos: baslik yok")

    if not mapped.isbn:
        mapped.problems.append("020$a yok: ISBN yok")

    if not mapped.authors:
        mapped.problems.append("100/700 yok: yazar yok")

    if mapped.library_code is None:
        mapped.problems.append("852$b yok: hangi kutuphane belirsiz")

    return mapped
