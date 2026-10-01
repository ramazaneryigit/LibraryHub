"""MARC21 in ISO 2709.

This is the format every library system exports and imports, which is why it is
the onboarding path: one file from one library is its whole collection. Nothing
here talks to a database or a network -- it turns bytes into records, and that is
testable on its own, which is the whole reason it is separate.

The format
----------
    leader     24 characters
    directory  12 characters per field, ending with 0x1E
    fields     the data, ending with 0x1D

A directory entry is `tag`(3) + `length`(4) + `offset`(5), and the offsets are
measured from the *base address* in the leader, not from the start of the record.
Getting that wrong produces records that parse and are wrong, so it is stated here
and asserted in the tests.

A field is either a control field -- `001` to `009`, one unbroken string -- or a
data field: two indicator characters, then subfields, each `0x1F` + one code
character + the value. `0x1E` ends the field. The subfield delimiter is byte 31,
not a dollar sign; a dollar sign only appears that way because older documentation
rendered it so.

Decoding
--------
Modern MARC21 is UTF-8 and that is the default. Older Turkish records are often
MARC-8 or a legacy single-byte code page, so a record that is not valid UTF-8
falls back to a permissive single-byte decode rather than failing. Failing would
reject exactly the older records a national catalogue most needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Iterator

__all__ = [
    "Field",
    "Record",
    "MarcError",
    "parse_records",
    "to_text",
]


FIELD_TERMINATOR = 0x1E
RECORD_TERMINATOR = 0x1D
SUBFIELD_DELIMITER = 0x1F

LEADER_LENGTH = 24
DIRECTORY_ENTRY_LENGTH = 12


class MarcError(ValueError):
    """A record that cannot be read. The message says which part."""


@dataclass
class Field:
    tag: str
    indicator1: str = " "
    indicator2: str = " "
    subfields: list[tuple[str, str]] = dataclass_field(default_factory=list)

    def get(self, code: str, default: str | None = None) -> str | None:
        """The first value of one subfield."""

        for key, value in self.subfields:
            if key == code:
                return value

        return default

    def all(self, code: str) -> list[str]:
        return [value for key, value in self.subfields if key == code]

    def is_control(self) -> bool:
        return not self.subfields and self.indicator1.isspace() and self.indicator2.isspace()

    def __str__(self) -> str:
        if self.subfields:
            body = " ".join(f"${key}{value}" for key, value in self.subfields)
            return f"{self.tag} {self.indicator1}{self.indicator2} {body}"

        return f"{self.tag} {self.indicator1}{self.indicator2}".rstrip()


@dataclass
class Record:
    leader: str
    fields: list[Field] = dataclass_field(default_factory=list)

    def first(self, tag: str) -> Field | None:
        for entry in self.fields:
            if entry.tag == tag:
                return entry

        return None

    def everything(self, tag: str) -> list[Field]:
        return [entry for entry in self.fields if entry.tag == tag]

    def value(self, tag: str, code: str | None = None) -> str | None:
        """One value, the way a caller usually wants it.

        With no `code` the field is read as control data -- `001`, `008` -- and
        with one, that subfield: `value("245", "a")` is the title.
        """

        entry = self.first(tag)

        if entry is None:
            return None

        if code is None:
            if entry.subfields:
                return entry.subfields[0][1]

            return None

        return entry.get(code)

    def values(self, tag: str, code: str | None = None) -> list[str]:
        out = []

        for entry in self.everything(tag):
            if code is None:
                out.append(entry.subfields[0][1] if entry.subfields else "")
            else:
                out.extend(entry.all(code))

        return out


def to_text(raw: bytes) -> str:
    """Bytes to text, preferring UTF-8 and refusing to lose a record over it."""

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _int(raw: bytes, label: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise MarcError(f"{label} is not a number: {raw!r}") from error


def _parse_one(block: bytes, *, strict: bool = True) -> Record:
    if len(block) < LEADER_LENGTH:
        raise MarcError(f"record is {len(block)} bytes, shorter than a leader")

    leader = block[:LEADER_LENGTH].decode("latin-1")

    # The length the leader claims and the length we have should agree. A file
    # trimmed by a transfer is the common cause of a disagreement, and saying so
    # is more useful than parsing whatever happens to be left.
    claimed = _int(block[0:5], "record length")

    if claimed != len(block) and strict:
        raise MarcError(
            f"leader says {claimed} bytes, the record has {len(block)}"
        )

    base = _int(block[12:17], "base address")

    if base > len(block):
        raise MarcError(f"base address {base} is past the end of a {len(block)} byte record")

    directory = block[LEADER_LENGTH:base]

    if not directory:
        raise MarcError("directory is empty")

    # The directory ends with a field terminator; everything after it in this
    # slice is what remains of the byte.
    if directory.endswith(bytes([FIELD_TERMINATOR])):
        directory = directory[:-1]

    record = Record(leader=leader)

    for start in range(0, len(directory), DIRECTORY_ENTRY_LENGTH):
        entry = directory[start:start + DIRECTORY_ENTRY_LENGTH]

        if len(entry) < DIRECTORY_ENTRY_LENGTH:
            if strict:
                raise MarcError(f"directory entry {start // 12} is truncated")

            break

        tag = entry[0:3].decode("latin-1")
        length = _int(entry[3:7], f"field {tag} length")
        offset = _int(entry[7:12], f"field {tag} offset")

        # Offsets are relative to the base address. Measured from the start of the
        # record they land somewhere plausible and wrong.
        at = base + offset
        raw = block[at:at + length]

        if len(raw) < length and strict:
            raise MarcError(
                f"field {tag} claims {length} bytes at {at}, "
                f"only {len(raw)} are there"
            )

        raw = raw.rstrip(bytes([FIELD_TERMINATOR]))

        if tag < "010":
            # A control field is one unbroken string: `001` is the record id,
            # `008` is fixed-length coded data.
            record.fields.append(
                Field(tag=tag, subfields=[("", to_text(raw))])
            )
            continue

        text = to_text(raw)

        if len(text) < 2:
            record.fields.append(Field(tag=tag))
            continue

        entry_field = Field(
            tag=tag,
            indicator1=text[0],
            indicator2=text[1],
        )

        for part in text[2:].split(chr(SUBFIELD_DELIMITER)):
            if not part:
                continue

            entry_field.subfields.append((part[0], part[1:]))

        record.fields.append(entry_field)

    return record


def parse_records(data: bytes, *, strict: bool = True) -> Iterator[Record]:
    """Every record in a file, in order.

    Iterated rather than returned as a list: a national catalogue export is
    hundreds of megabytes and there is no reason to hold it all at once.
    """

    position = 0
    total = len(data)

    while position < total:
        # Between records there is sometimes a newline or padding.
        while position < total and data[position] in (0x0A, 0x0D, 0x00, 0x20):
            position += 1

        if position >= total:
            return

        if total - position < LEADER_LENGTH:
            if strict:
                raise MarcError(f"{total - position} trailing bytes are not a record")

            return

        try:
            length = _int(data[position:position + 5], "record length")
        except MarcError:
            if strict:
                raise

            return

        if length <= 0 or position + length > total:
            # The leader's length is the only reliable way to find the next record,
            # so when it is wrong there is nothing trustworthy left to read.
            if strict:
                raise MarcError(
                    f"record at {position} claims {length} bytes, "
                    f"only {total - position} remain"
                )

            return

        block = data[position:position + length]

        yield _parse_one(block, strict=strict)

        position += length
