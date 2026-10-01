"""MARC21 to our model.

The mapping is where every judgement about a record is made, so it is where a
mistake costs most. It is pure, so it can be tested without a database, and these
tests build records byte by byte rather than from a fixture file whose provenance
nobody can check.
"""

import unittest

from app.core.marc import parse_records
from app.core.marc_mapping import map_record, normalize_library_code


def build(fields):
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

    return "".join(leader).encode("ascii") + directory + body + b"\x1d"


D = "\x1f"


def mapped(fields):
    return map_record(next(parse_records(build(fields))))


class MappingTests(unittest.TestCase):
    def test_title_and_subtitle_are_separate_and_lose_their_punctuation(self):
        result = mapped([
            ("245", f"10{D}aSuç ve Ceza :{D}broman /{D}cFyodor Dostoyevski."),
        ])

        # The colon belongs to the display of the field, not to the subtitle.
        self.assertEqual(result.title, "Suç ve Ceza")
        self.assertEqual(result.subtitle, "roman")

    def test_an_isbn_loses_how_it_is_bound(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("020", f"  {D}a9789750000011 (pbk.)"),
            ("020", f"  {D}a9789750000028"),
        ])

        self.assertEqual(result.isbn, ["9789750000011", "9789750000028"])

    def test_the_main_entry_is_marked_and_roles_are_kept(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("100", f"1 {D}aDostoyevski, Fyodor,{D}d1821-1881."),
            ("700", f"1 {D}aMazlum Beyhan,{D}eçeviren."),
        ])

        self.assertEqual(len(result.authors), 2)
        self.assertTrue(result.authors[0].main)
        self.assertEqual(result.authors[0].dates, "1821-1881")
        self.assertFalse(result.authors[1].main)
        self.assertEqual(result.authors[1].role, "çeviren")

    def test_language_comes_from_041_and_falls_back_to_the_fixed_field(self):
        with_041 = mapped([
            ("245", f"10{D}aBir kitap"),
            ("041", f"  {D}atur{D}aeng"),
        ])
        self.assertEqual(with_041.language, "tur")

        without = mapped([
            ("245", f"10{D}aBir kitap"),
            ("008", "240101s2026    tu            000 0 tur d"),
        ])
        self.assertEqual(without.language, "tur")

    def test_publication_prefers_264_and_accepts_the_older_260(self):
        new = mapped([
            ("245", f"10{D}aBir kitap"),
            ("264", f" 1{D}aAnkara :{D}bTTK,{D}c2026."),
        ])
        self.assertEqual(new.publication_place, "Ankara")
        self.assertEqual(new.publisher, "TTK")
        self.assertEqual(new.publication_date, "2026")

        old = mapped([
            ("245", f"10{D}aBir kitap"),
            ("260", f"  {D}aAnkara :{D}bTTK,{D}c2026."),
        ])
        self.assertEqual(old.publisher, "TTK")

    def test_a_subject_keeps_its_subdivisions(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("650", f"0 {D}aRus edebiyatı{D}xRoman."),
        ])

        self.assertEqual(result.subjects, ["Rus edebiyatı - Roman"])

    def test_the_shelf_address_comes_from_the_holding_before_the_classification(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("082", f"  {D}a891.73"),
            ("852", f"  {D}bTR-KKU{D}hPL248{D}i.D67{D}j2026"),
        ])

        self.assertEqual(result.call_number, "PL248 .D67")
        self.assertEqual(result.library_code.raw, "TR-KKU")

    def test_the_classification_is_the_fallback(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("082", f"  {D}a891.73"),
        ])

        self.assertEqual(result.call_number, "891.73")

    def test_a_library_code_is_normalized_so_one_library_stays_one(self):
        for written in ("TR-KKU", "tr-kku", " TR KKU ", "tr_kku"):
            with self.subTest(written=written):
                self.assertEqual(normalize_library_code(written), "TR-KKU")

    def test_copies_come_from_the_piece_designation(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("852", f"  {D}bTR-KKU"),
            ("876", f"  {D}a000123{D}pKKU-123456"),
            ("876", f"  {D}a000124{D}pKKU-123457"),
        ])

        self.assertEqual([item.barcode for item in result.items], ["KKU-123456", "KKU-123457"])

    def test_a_record_without_a_library_code_gives_no_holding(self):
        """The linchpin: `852$b` is an opaque code, and guessing it would invent
        libraries that do not exist."""

        result = mapped([("245", f"10{D}aBir kitap")])

        self.assertTrue(result.usable)
        self.assertFalse(result.gives_a_holding)
        self.assertIn("852$b yok: hangi kutuphane belirsiz", result.problems)

    def test_a_record_with_a_library_code_can_place_a_book(self):
        result = mapped([
            ("245", f"10{D}aBir kitap"),
            ("852", f"  {D}bTR-KKU"),
        ])

        self.assertTrue(result.gives_a_holding)

    def test_a_titleless_record_is_not_usable(self):
        result = mapped([
            ("001", "KKU0001"),
            ("100", f"1 {D}aYazar, Bir"),
        ])

        self.assertFalse(result.usable)
        self.assertIn("245$a bos: baslik yok", result.problems)

    def test_every_problem_is_named_and_countable(self):
        """The report a library is shown before handing over a collection.

        Each entry is something somebody could go and fix in the source record,
        which is what makes it a report rather than a complaint.
        """

        result = mapped([("001", "KKU0001")])

        self.assertEqual(result.problems, [
            "245$a bos: baslik yok",
            "020$a yok: ISBN yok",
            "100/700 yok: yazar yok",
            "852$b yok: hangi kutuphane belirsiz",
        ])

    def test_a_complete_record_reports_no_problems(self):
        result = mapped([
            ("001", "KKU0001"),
            ("020", f"  {D}a9789750000011"),
            ("100", f"1 {D}aDostoyevski, Fyodor."),
            ("245", f"10{D}aSuç ve Ceza"),
            ("852", f"  {D}bTR-KKU"),
        ])

        self.assertEqual(result.problems, [])
        self.assertTrue(result.usable)
        self.assertTrue(result.gives_a_holding)

    def test_the_summary_line_names_what_was_read(self):
        result = mapped([
            ("245", f"10{D}aSuç ve Ceza"),
            ("100", f"1 {D}aDostoyevski, Fyodor."),
            ("020", f"  {D}a9789750000011"),
            ("852", f"  {D}bTR-KKU"),
            ("876", f"  {D}pKKU-1"),
        ])

        self.assertEqual(
            result.summary(),
            "'Suç ve Ceza' | 1 yazar | ISBN 9789750000011 | kutuphane TR-KKU | 1 nusha",
        )


if __name__ == "__main__":
    unittest.main()
