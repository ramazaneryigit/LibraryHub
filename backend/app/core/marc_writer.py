"""Writing MARC21 in ISO 2709 and MARCXML.

The inverse of `marc`, and pure for the same reason: bytes out of records, no
database, no network. That makes the strongest test available possible -- write a
record, read it back with the parser, and see the same thing -- and a round trip
catches an offset or a length that a hand-written expectation would not.

Why export at all
-----------------
An institution's first question before handing over a collection is whether it can
get it back. If the answer is no, there is no agreement, and there is no union
catalogue. So this is not a courtesy feature; it is the precondition.

It is also cheaper than it looks: the codec already existed for reading, and this
is the same codec running the other way.

What it writes
--------------
The standard fields every library system reads -- 245, 100/700, 264, 020, 650,
852, 876 -- because a file only we can read is not a way out. The RDA fields named
in `docs/rda-uygulanabilirligi.md` are the second step: `040$e rda`, 336/337/338
and the controlled relators need columns we do not have yet, and writing a field
we cannot populate would be inventing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence
from xml.sax.saxutils import escape, quoteattr

from .marc import FIELD_TERMINATOR, RECORD_TERMINATOR, SUBFIELD_DELIMITER

__all__ = [
    "MarcField",
    "MarcRecord",
    "from_mapped",
    "to_iso2709",
    "to_marcxml",
]


# A byte offset in the directory is four digits, and a field length is four more.
# A field longer than 9999 bytes cannot be expressed -- which is a real limit of
# the format rather than of this code, and being told is better than a corrupt
# directory.
MAX_FIELD_BYTES = 9999


@dataclass
class MarcField:
    tag: str
    indicator1: str = " "
    indicator2: str = " "
    # An empty code marks a control field, whose value is one unbroken string.
    subfields: list[tuple[str, str]] = None

    def __post_init__(self):
        if self.subfields is None:
            self.subfields = []

    def render(self) -> str:
        if not self.subfields:
            return ""

        if self.subfields[0][0] == "":
            return self.subfields[0][1]

        body = "".join(
            chr(SUBFIELD_DELIMITER) + code + value
            for code, value in self.subfields
        )

        return self.indicator1 + self.indicator2 + body


@dataclass
class MarcRecord:
    fields: list[MarcField]
    status: str = "n"
    record_type: str = "a"
    bibliographic_level: str = "m"
    coding_scheme: str = "a"  # 'a' is UTF-8
    cataloguing_form: str = "i"  # 'i' is ISBD punctuation included

    def field(self, tag: str) -> MarcField | None:
        for entry in self.fields:
            if entry.tag == tag:
                return entry

        return None


def _leader(record: MarcRecord, length: int, base: int) -> str:
    """A 24 character leader, built by position.

    Set by index rather than by a format string: the positions are fixed and
    unrelated to each other, and a template that drifts by one character produces
    a file that parses into the wrong fields.
    """

    leader = list("00000nam a2200000 a 4500")
    leader[0:5] = f"{length:05d}"
    leader[5] = record.status
    leader[6] = record.record_type
    leader[7] = record.bibliographic_level
    leader[10] = record.coding_scheme
    leader[12:17] = f"{base:05d}"
    leader[18] = record.cataloguing_form

    return "".join(leader)


def _encode(record: MarcRecord) -> bytes:
    body = b""
    directory = b""

    for entry in record.fields:
        raw = entry.render().encode("utf-8") + bytes([FIELD_TERMINATOR])

        if len(raw) > MAX_FIELD_BYTES:
            raise ValueError(
                f"field {entry.tag} is {len(raw)} bytes; the directory can only "
                f"express {MAX_FIELD_BYTES}"
            )

        directory += f"{entry.tag}{len(raw):04d}{len(body):05d}".encode("ascii")
        body += raw

    directory += bytes([FIELD_TERMINATOR])

    base = 24 + len(directory)
    length = base + len(body) + 1

    leader = _leader(record, length, base).encode("ascii")

    return leader + directory + body + bytes([RECORD_TERMINATOR])


def to_iso2709(records: Iterable[MarcRecord]) -> bytes:
    """A file of records, in the order given.

    `.mrc`, the format every library system imports.
    """

    return b"".join(_encode(record) for record in records)


def to_marcxml(records: Iterable[MarcRecord], *, collection: bool = True) -> str:
    """The same records as MARCXML.

    Some systems prefer it, and unlike ISO 2709 it is readable in a text editor,
    which matters when somebody is checking an export by eye rather than feeding
    it to a program.
    """

    parts = []

    if collection:
        parts.append(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<collection xmlns="http://www.loc.gov/MARC21/slim">'
        )

    for record in records:
        parts.append("<record>")
        parts.append(f"<leader>{escape(_leader_for(record))}</leader>")

        for entry in record.fields:
            parts.append(f"<controlfield tag={quoteattr(entry.tag)}>"
                         f"{escape(entry.render())}</controlfield>"
                         if not entry.subfields or entry.subfields[0][0] == ""
                         else _datafield(entry))

        parts.append("</record>")

    if collection:
        parts.append("</collection>")

    return "".join(parts)


def _leader_for(record: MarcRecord) -> str:
    # The lengths in a MARCXML leader are not meaningful -- XML carries its own --
    # and the conventional zeros are what exporters write.
    return _leader(record, 0, 0)


def _datafield(entry: MarcField) -> str:
    subfields = "".join(
        f"<subfield code={quoteattr(code)}>{escape(value)}</subfield>"
        for code, value in entry.subfields
    )

    return (
        f"<datafield tag={quoteattr(entry.tag)} "
        f"ind1={quoteattr(entry.indicator1)} "
        f"ind2={quoteattr(entry.indicator2)}>{subfields}</datafield>"
    )


def from_mapped(mapped) -> MarcRecord:
    """A `MappedRecord` back into MARC.

    The inverse of `marc_mapping.map_record`, and deliberately only as rich as
    that mapping is: what we did not read on the way in we cannot write on the way
    out, and a field invented here would be a claim about a book we do not have.
    """

    fields: list[MarcField] = []

    if mapped.control_number:
        fields.append(MarcField("001", subfields=[("", mapped.control_number)]))

    if mapped.language:
        fields.append(
            MarcField("041", " ", " ", [("a", mapped.language)])
        )

    for isbn in mapped.isbn:
        fields.append(MarcField("020", " ", " ", [("a", isbn)]))

    for author in mapped.authors:
        subfields = [("a", author.name)]

        if author.dates:
            subfields.append(("d", author.dates))

        if author.role:
            subfields.append(("e", author.role))

        if author.relator:
            subfields.append(("4", author.relator))

        fields.append(
            MarcField("100" if author.main else "700", "1", " ", subfields)
        )

    if mapped.title:
        title = [("a", mapped.title)]

        if mapped.subtitle:
            title.append(("b", mapped.subtitle))

        if mapped.authors:
            title.append(("c", "; ".join(a.name for a in mapped.authors)))

        fields.append(MarcField("245", "1", "0", title))

    if mapped.edition_statement:
        fields.append(MarcField("250", " ", " ", [("a", mapped.edition_statement)]))

    if mapped.publisher or mapped.publication_place or mapped.publication_date:
        publication = []

        if mapped.publication_place:
            publication.append(("a", mapped.publication_place + " :"))

        if mapped.publisher:
            publication.append(("b", mapped.publisher + ","))

        if mapped.publication_date:
            publication.append(("c", mapped.publication_date))

        fields.append(MarcField("264", " ", "1", publication))

    for subject in mapped.subjects:
        # Subdivisions were joined with a dash on the way in, and split again here
        # so that `650$x` stays a subdivision rather than becoming part of the
        # heading.
        head, _, rest = subject.partition(" - ")
        subfields = [("a", head)]

        for subdivision in [part for part in rest.split(" - ") if part]:
            subfields.append(("x", subdivision))

        fields.append(MarcField("650", "0", " ", subfields))

    if mapped.items:
        for item in mapped.items:
            subfields = []

            if item.barcode:
                subfields.append(("p", item.barcode))

            if item.shelfmark:
                subfields.append(("l", item.shelfmark))

            if item.note:
                subfields.append(("z", item.note))

            fields.append(MarcField("876", " ", " ", subfields))

    if mapped.library_code:
        holding = [("b", mapped.library_code.raw)]

        if mapped.call_number:
            head, _, suffix = mapped.call_number.partition(" ")
            holding.append(("h", head))

            if suffix:
                holding.append(("i", suffix))

        fields.append(MarcField("852", " ", " ", holding))

    return MarcRecord(fields=fields)
