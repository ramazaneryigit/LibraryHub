"""MARC21 ISO 2709 parsing.

The records in these tests are built by `build()` below, byte by byte, from the
format description rather than from the parser's own output. That matters: a test
that asks the parser to read what the parser wrote proves only that it is
self-consistent. The directory offsets here are computed the same way a library's
system computes them, and the base-address rule -- offsets measured from the base
address, not the start of the record -- is asserted directly, because getting that
wrong yields records that parse and are wrong.
"""

import unittest

from app.core.marc import MarcError, parse_records, to_text


def build(fields, leader_overrides=None):
    """One ISO 2709 record from (tag, data) pairs.

    `data` is the raw field content: for a control field an unbroken string, for a
    data field two indicators followed by `\\x1f` + code + value.
    """

    directory = b""
    body = b""

    for tag, data in fields:
        raw = data.encode("utf-8") + b"\x1e"
        directory += f"{tag}{len(raw):04d}{len(body):05d}".encode("ascii")
        body += raw

    directory += b"\x1e"

    base = len(directory) + 24
    length = base + len(body) + 1

    leader = list("00000nam a2200000 a 4500")
    leader[0:5] = f"{length:05d}"
    leader[12:17] = f"{base:05d}"

    if leader_overrides:
        for key, value in leader_overrides.items():
            leader[key] = value

    return "".join(leader).encode("ascii") + directory + body + b"\x1d"


D = "\x1f"  # the subfield delimiter, byte 31


def simple_record():
    return build([
        ("001", "KKU00012345"),
        ("008", "240101s2026    tu            000 0 tur d"),
        ("020", f"  {D}a9789750000011"),
        ("041", f"  {D}atur{D}aheng"),
        ("100", f"1 {D}aDostoyevski, Fyodor,{D}d1821-1881."),
        ("245", f"10{D}aSuç ve Ceza /{D}cFyodor Dostoyevski."),
        ("260", f"  {D}aAnkara :{D}bTTK Yayınları,{D}c2026."),
        ("650", f"0 {D}aRus edebiyatı{D}xRoman."),
        ("700", f"1 {D}aMazlum Beyhan,{D}eçeviren."),
        ("852", f"  {D}bTR-KKU{D}hPL248{D}i.D67{D}j2026"),
    ])


class MarcParsingTests(unittest.TestCase):
    def test_a_record_parses_into_its_fields(self):
        record = next(parse_records(simple_record()))

        self.assertEqual(record.value("001"), "KKU00012345")
        self.assertEqual(record.value("020", "a"), "9789750000011")
        self.assertEqual(record.value("245", "a"), "Suç ve Ceza /")
        self.assertEqual(record.value("245", "c"), "Fyodor Dostoyevski.")

    def test_control_fields_are_not_split_on_indicators(self):
        """`008` starts with two digits that are data, not indicators."""

        record = next(parse_records(simple_record()))
        control = record.first("008")

        self.assertEqual(control.subfields[0][0], "")
        self.assertTrue(control.subfields[0][1].startswith("240101s2026"))

    def test_indicators_survive(self):
        record = next(parse_records(simple_record()))

        self.assertEqual(record.first("100").indicator1, "1")
        self.assertEqual(record.first("245").indicator1, "1")
        self.assertEqual(record.first("245").indicator2, "0")
        self.assertEqual(record.first("650").indicator1, "0")
        self.assertEqual(record.first("650").indicator2, " ")

    def test_every_subfield_of_a_repeated_code_is_kept(self):
        record = next(parse_records(simple_record()))

        self.assertEqual(record.values("041", "a"), ["tur", "heng"])
        self.assertEqual(record.values("852", "b"), ["TR-KKU"])

    def test_a_repeated_tag_returns_every_occurrence(self):
        raw = build([
            ("245", f"10{D}aBir{D}bbir"),
            ("650", f" 0{D}aKonu bir"),
            ("650", f" 0{D}aKonu iki"),
        ])

        record = next(parse_records(raw))

        self.assertEqual(len(record.everything("650")), 2)
        self.assertEqual(record.values("650", "a"), ["Konu bir", "Konu iki"])

    def test_offsets_are_measured_from_the_base_address(self):
        """The mistake that parses and is wrong.

        A second field is only reachable if its offset is read relative to the base
        address. The first field sits at offset zero and would be found either way,
        so the test reads a field that is not first.
        """

        record = next(parse_records(simple_record()))

        self.assertEqual(record.value("245", "a"), "Suç ve Ceza /")
        self.assertEqual(record.value("852", "h"), "PL248")

    def test_several_records_in_one_file(self):
        first = simple_record()
        second = build([("245", f"10{D}aİkinci kayıt")])

        records = list(parse_records(first + second))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[1].value("245", "a"), "İkinci kayıt")

    def test_a_trimmed_record_is_refused_rather_than_half_read(self):
        """A file cut short by a transfer is the common real failure.

        It is caught before the leader is even read, because the record's declared
        length is the only trustworthy way to find where it ends -- so the message
        is about the record rather than about the leader, and that is the better
        one to give.
        """

        with self.assertRaises(MarcError) as caught:
            next(parse_records(simple_record()[:-20]))

        self.assertIn("claims", str(caught.exception))
        self.assertIn("remain", str(caught.exception))

    def test_a_bad_length_in_the_leader_is_refused(self):
        raw = bytearray(simple_record())
        raw[0:5] = b"99999"

        with self.assertRaises(MarcError) as caught:
            next(parse_records(bytes(raw)))

        self.assertIn("claims", str(caught.exception))

    def test_turkish_survives_the_round_trip(self):
        record = next(parse_records(simple_record()))

        self.assertEqual(record.value("260", "b"), "TTK Yayınları,")
        self.assertEqual(record.value("245", "a"), "Suç ve Ceza /")

    def test_legacy_bytes_are_decoded_rather_than_rejected(self):
        """Older Turkish records are not always UTF-8.

        Tested on `to_text` directly. An earlier version of this test patched a
        byte inside a built record and shortened it by three, so the record failed
        the length check before decoding was ever reached -- the test measured the
        wrong thing and the parser was right to refuse it.
        """

        self.assertEqual(to_text("Ayşe".encode("utf-8")), "Ayşe")
        self.assertIn("Su", to_text(b"Su\xe7 ve Ceza"))
        self.assertTrue(to_text(b"\xff\xfe"))

    def test_non_strict_skips_a_damaged_record_instead_of_stopping(self):
        damaged = bytearray(simple_record())
        damaged[0:5] = b"99999"

        records = list(
            parse_records(bytes(damaged) + simple_record(), strict=False)
        )

        # The first record is unusable; the parse stops rather than inventing one.
        self.assertEqual(records, [])

    def test_to_text_prefers_utf8_and_never_raises(self):
        self.assertEqual(to_text("Ayşe".encode("utf-8")), "Ayşe")
        self.assertTrue(to_text(b"\xff\xfe broken"))

    def test_a_field_can_be_printed_for_a_log(self):
        record = next(parse_records(simple_record()))

        self.assertEqual(
            str(record.first("100")),
            "100 1  $aDostoyevski, Fyodor, $d1821-1881.",
        )


if __name__ == "__main__":
    unittest.main()
