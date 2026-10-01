"""Authority matching.

The tests are about restraint as much as about matching. Finding candidates is
easy; the damage is done by merging on weak evidence, and the error is invisible
once made -- one scholar's work attributed to another, and nothing in the record
says it happened.
"""

import unittest

from app.core.authority import Candidate, fold, match_key, parse_name, similarity, suggest


class FoldingTests(unittest.TestCase):
    def test_turkish_letters_fold_the_way_turkish_does(self):
        """`İnce` and `Ince` are one author. A catalogue where they are not has
        split its own literature."""

        self.assertEqual(fold("İnce"), "ince")
        self.assertEqual(fold("Ince"), "ince")
        self.assertEqual(fold("IŞIK"), "isik")
        self.assertEqual(fold("Işık"), "isik")

    def test_accents_are_removed_for_comparison(self):
        self.assertEqual(fold("Dostoyevski"), fold("Dostoyevski"))
        self.assertEqual(fold("Достоевский"), fold("Достоевский"))
        self.assertEqual(fold("Öztürk"), "ozturk")

    def test_punctuation_is_not_part_of_a_name(self):
        self.assertEqual(fold("Dostoyevski, F."), "dostoyevski f")
        self.assertEqual(fold("Dostoyevski  F"), "dostoyevski f")

    def test_nothing_folds_to_nothing(self):
        for value in (None, "", "   ", ".,;"):
            with self.subTest(value=value):
                self.assertEqual(fold(value), "")


class NameParsingTests(unittest.TestCase):
    def test_the_inverted_form_and_the_natural_form_agree(self):
        self.assertEqual(parse_name("Dostoyevski, Fyodor"), ("dostoyevski", ["fyodor"]))
        self.assertEqual(parse_name("Fyodor Dostoyevski"), ("dostoyevski", ["fyodor"]))

    def test_a_particle_does_not_become_the_surname(self):
        self.assertEqual(parse_name("van der Berg, Jan"), ("berg", ["jan"]))
        self.assertEqual(parse_name("Jan van der Berg"), ("berg", ["jan", "van", "der"]))

    def test_a_single_name_is_a_surname(self):
        self.assertEqual(parse_name("Anonim"), ("anonim", []))

    def test_dates_and_roles_are_stripped_from_a_name(self):
        self.assertEqual(parse_name("Kaya, Bilge, 1970-"), ("kaya", ["bilge"]))
        self.assertEqual(parse_name("Kaya, Bilge (editör)"), ("kaya", ["bilge"]))


class KeyTests(unittest.TestCase):
    def test_the_weak_key_is_surname_and_initials(self):
        self.assertEqual(match_key("Dostoyevski, Fyodor"), "dostoyevski|f")
        self.assertEqual(match_key("Fyodor Dostoyevski"), "dostoyevski|f")

    def test_spelling_differences_do_not_share_a_key(self):
        """Why the key alone would not be enough.

        `Dostoevsky` and `Dostoyevski` differ by one letter, and the second name
        adds an initial on top, so the keys are different -- and they should be,
        because the key is an exact thing. What rescues the pair is character
        closeness, and the two assertions below are the division of labour: the
        key decides nothing here, and the name still surfaces.
        """

        self.assertNotEqual(
            match_key("Dostoyevski, Fyodor"),
            match_key("Dostoevsky, Fyodor Mihayloviç"),
        )

        found = suggest(
            "Dostoevsky, Fyodor Mihayloviç",
            [{"entity_id": "1", "name": "Dostoyevski, Fyodor"}],
        )

        self.assertTrue(found, "bir harf farki aday bulmayi engellememeli")
        self.assertFalse(found[0].decides)

    def test_a_name_with_nothing_in_it_has_no_key(self):
        self.assertEqual(match_key(None), "")
        self.assertEqual(match_key("..."), "")


class SimilarityTests(unittest.TestCase):
    def test_word_order_does_not_matter(self):
        self.assertEqual(similarity("Dostoyevski, Fyodor", "Fyodor Dostoyevski"), 1.0)

    def test_a_shared_surname_alone_is_partial(self):
        score = similarity("Dostoyevski, Fyodor", "Dostoyevski, Aleksey")

        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_unrelated_names_score_nothing(self):
        self.assertEqual(similarity("Dostoyevski, Fyodor", "Kaya, Bilge"), 0.0)


class SuggestingTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = [
            {"entity_id": "1", "name": "Dostoyevski, Fyodor", "orcid": "0000-0002-1825-0097"},
            {"entity_id": "2", "name": "Dostoyevski, Aleksey"},
            {"entity_id": "3", "name": "Kaya, Bilge"},
        ]

    def test_an_orcid_decides(self):
        found = suggest(
            "Fyodor Mihayloviç Dostoyevski",
            self.catalogue,
            orcid="https://orcid.org/0000-0002-1825-0097",
        )

        self.assertEqual(found[0].entity_id, "1")
        self.assertTrue(found[0].decides)
        self.assertEqual(found[0].reason, "ayni ORCID")

    def test_agreeing_dates_decide(self):
        found = suggest(
            "Dostoevsky, Fyodor",
            [{"entity_id": "9", "name": "Dostoevsky, Fyodor", "dates": "1821-1881"}],
            dates="1821-1881",
        )

        self.assertTrue(found[0].decides)

    def test_a_spelling_variant_never_decides_on_its_own(self):
        """The whole point of the module.

        `Dostoyevski, F.` suggests Fyodor and also suggests every other
        Dostoyevski with an F. Merging on that is how one scholar's work is
        attributed to another, and once it is done nothing in the record says so.
        """

        found = suggest("Dostoevsky, F.", self.catalogue)

        self.assertTrue(found)
        self.assertTrue(all(not candidate.decides for candidate in found))
        self.assertEqual(found[0].entity_id, "1")
        self.assertIn(found[0].reason, ("ayni soyad ve bas harfler", "benzer ad"))

    def test_candidates_come_back_best_first(self):
        found = suggest("Dostoyevski, Fyodor", self.catalogue)

        self.assertEqual(found[0].entity_id, "1")
        self.assertGreaterEqual(found[0].score, found[-1].score)

    def test_an_unrelated_name_finds_nothing(self):
        found = suggest("Tamamen Baska, Birisi", self.catalogue)

        self.assertEqual(found, [])

    def test_an_empty_name_finds_nothing(self):
        self.assertEqual(suggest(None, self.catalogue), [])
        self.assertEqual(suggest("", self.catalogue), [])

    def test_the_forty_spellings_case(self):
        """The situation a thousand libraries create, in one assertion.

        Four spellings of one author must produce one deciding candidate -- or,
        when there is no strong evidence, one queue entry -- and not four people.
        """

        spellings = [
            "Dostoyevski, Fyodor",
            "Dostoevsky, Fyodor",
            "Fyodor Dostoyevski",
            "Dostoyevski, Fyodor Mihayloviç",
        ]

        catalogue = [
            {"entity_id": str(index), "name": spelling}
            for index, spelling in enumerate(spellings)
        ]

        found = suggest("Dostoevsky, F.", catalogue)

        self.assertTrue(found)
        self.assertTrue(all(candidate.strength == "weak" for candidate in found))

    def test_an_identical_name_decides(self):
        """Not proof in the abstract -- two people can share a name -- but it is
        what the catalogue already keyed on, and treating it as merely similar
        creates a duplicate record and then queues a 1.00 match to it."""

        found = suggest("TTK Yayınları", [{"entity_id": "1", "name": "TTK Yayinlari"}])

        self.assertEqual(found[0].entity_id, "1")
        self.assertTrue(found[0].decides)
        self.assertEqual(found[0].reason, "ayni ad")

    def test_a_candidate_knows_whether_it_decides(self):
        self.assertTrue(Candidate("1", "x", 1.0, "strong", "ayni ORCID").decides)
        self.assertFalse(Candidate("1", "x", 0.9, "weak", "benzer ad").decides)


if __name__ == "__main__":
    unittest.main()
