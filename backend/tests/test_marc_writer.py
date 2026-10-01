"""MARC export.

The round trip is the test that matters: map a record, write it, read it back with
the parser and map it again, and expect the same thing. A hand-written expectation
would pass while an offset was wrong; a round trip cannot, because both halves have
to agree about where a field ends.
"""

import unittest

from app.core.marc import parse_records
from app.core.marc_mapping import MappedAuthor, MappedRecord, NormalizedCode, map_record
from app.core.marc_writer import MarcField, MarcRecord, from_mapped, to_iso2709, to_marcxml


def sample() -> MappedRecord:
    return MappedRecord(
        control_number="KKU0000001",
        title="Suç ve Ceza",
        subtitle="roman",
        authors=[
            MappedAuthor(name="Dostoyevski, Fyodor", dates="1821-1881", main=True),
            MappedAuthor(name="Mazlum Beyhan", role="çeviren"),
        ],
        isbn=["9789750000011"],
        language="tur",
        publication_place="Ankara",
        publisher="TTK Yayınları",
        publication_date="2026",
        edition_statement="3. baskı",
        subjects=["Rus edebiyatı - Roman"],
        call_number="PL248 .D67",
        library_code=NormalizedCode(raw="TR-KKU", normalized="TR-KKU"),
    )


def round_trip(record: MappedRecord) -> MappedRecord:
    return map_record(next(parse_records(to_iso2709([from_mapped(record)]))))


class RoundTripTests(unittest.TestCase):
    def test_a_record_survives_being_written_and_read_back(self):
        original = sample()
        back = round_trip(original)

        self.assertEqual(back.control_number, original.control_number)
        self.assertEqual(back.title, original.title)
        self.assertEqual(back.subtitle, original.subtitle)
        self.assertEqual(back.isbn, original.isbn)
        self.assertEqual(back.language, original.language)
        self.assertEqual(back.publisher, original.publisher)
        self.assertEqual(back.publication_place, original.publication_place)
        self.assertEqual(back.publication_date, original.publication_date)
        self.assertEqual(back.edition_statement, original.edition_statement)
        self.assertEqual(back.subjects, original.subjects)
        self.assertEqual(back.call_number, original.call_number)
        self.assertEqual(back.library_code.raw, original.library_code.raw)

    def test_authors_survive_with_their_main_marking_and_role(self):
        back = round_trip(sample())

        self.assertEqual(len(back.authors), 2)
        self.assertEqual(back.authors[0].name, "Dostoyevski, Fyodor")
        self.assertEqual(back.authors[0].dates, "1821-1881")
        self.assertTrue(back.authors[0].main)
        self.assertEqual(back.authors[1].role, "çeviren")
        self.assertFalse(back.authors[1].main)

    def test_turkish_survives_the_round_trip(self):
        """UTF-8 in, UTF-8 out. A catalogue that loses 'ş' loses its own records."""

        back = round_trip(sample())

        self.assertEqual(back.title, "Suç ve Ceza")
        self.assertEqual(back.publisher, "TTK Yayınları")

    def test_a_record_with_no_holding_still_round_trips(self):
        original = MappedRecord(title="Bir kitap", control_number="X1")
        back = round_trip(original)

        self.assertEqual(back.title, "Bir kitap")
        self.assertIsNone(back.library_code)

    def test_copies_survive(self):
        original = sample()
        from app.core.marc_mapping import ItemRef

        original.items = [ItemRef(barcode="KKU-123456", shelfmark="A-12")]

        back = round_trip(original)

        self.assertEqual([item.barcode for item in back.items], ["KKU-123456"])


class StructureTests(unittest.TestCase):
    def test_the_leader_length_matches_the_bytes_written(self):
        """The one field a reader trusts to find the next record."""

        raw = to_iso2709([from_mapped(sample())])

        self.assertEqual(int(raw[0:5]), len(raw))
        self.assertEqual(raw[-1:], b"\x1d")

    def test_the_base_address_points_at_the_first_field(self):
        """Where the directory ends and the field data begins.

        The base address is the start of the variable fields area, not the start
        of the directory -- an earlier version of this test expected the tag `001`
        there and was wrong, because the tag lives in the directory and the base
        address points past it.
        """

        raw = to_iso2709([from_mapped(sample())])
        base = int(raw[12:17])

        # The directory ends with a field terminator...
        self.assertEqual(raw[base - 1:base], b"\x1e")

        # ...and the first field's data begins immediately after it.
        self.assertEqual(raw[base:base + 10], b"KKU0000001")

        # The tag itself is in the directory, before the base address.
        self.assertEqual(raw[24:27], b"001")

    def test_several_records_are_written_one_after_another(self):
        raw = to_iso2709([
            from_mapped(MappedRecord(title="Birinci", control_number="1")),
            from_mapped(MappedRecord(title="İkinci", control_number="2")),
        ])

        records = list(parse_records(raw))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[1].value("245", "a"), "İkinci")

    def test_a_field_too_long_for_the_directory_is_refused(self):
        """A real limit of the format: four digits of length, and no more."""

        record = MarcRecord(fields=[MarcField("500", subfields=[("a", "x" * 10000)])])

        with self.assertRaises(ValueError) as caught:
            to_iso2709([record])

        self.assertIn("9999", str(caught.exception))

    def test_a_control_field_is_written_without_indicators(self):
        record = MarcRecord(fields=[MarcField("001", subfields=[("", "KKU1")])])
        raw = to_iso2709([record])

        back = next(parse_records(raw))

        self.assertEqual(back.value("001"), "KKU1")

    def test_marcxml_carries_the_same_values(self):
        xml = to_marcxml([from_mapped(sample())])

        self.assertIn("http://www.loc.gov/MARC21/slim", xml)
        self.assertIn('<datafield tag="245" ind1="1" ind2="0">', xml)
        self.assertIn("<subfield code=\"a\">Suç ve Ceza</subfield>", xml)
        self.assertIn('<controlfield tag="001">KKU0000001</controlfield>', xml)

    def test_marcxml_escapes_what_xml_cannot_hold(self):
        record = MarcRecord(fields=[MarcField("245", "1", "0", [("a", "A & B < C")])])

        xml = to_marcxml([record])

        self.assertIn("A &amp; B &lt; C", xml)
        self.assertNotIn("A & B < C", xml)


if __name__ == "__main__":
    unittest.main()
