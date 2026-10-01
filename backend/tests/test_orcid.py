"""ORCID iD handling.

The check digit is the reason this is a unit test rather than an integration one:
a wrong digit produces a *valid-looking* iD, and if we accept it we create a second
person for somebody who already has a record. That is silent, permanent and
exactly the class of bug the catalogue cannot afford.
"""

import unittest

from app.core.orcid import is_valid_orcid, normalize_orcid


class OrcidTests(unittest.TestCase):
    def test_a_real_orcid_is_accepted(self):
        # The example ORCID uses in its own documentation, and a second real one.
        self.assertEqual(
            normalize_orcid("0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )
        self.assertEqual(
            normalize_orcid("0000-0001-5109-3700"),
            "0000-0001-5109-3700",
        )

    def test_the_same_id_written_four_ways_is_one_id(self):
        """Two spellings of one iD would be two people."""

        expected = "0000-0002-1825-0097"

        for written in (
            "0000-0002-1825-0097",
            "0000000218250097",
            "https://orcid.org/0000-0002-1825-0097",
            "  0000-0002-1825-0097  ",
        ):
            with self.subTest(written=written):
                self.assertEqual(normalize_orcid(written), expected)

    def test_a_wrong_check_digit_is_refused(self):
        """The whole point: 0098 looks right and is not an iD."""

        self.assertIsNone(normalize_orcid("0000-0002-1825-0098"))
        self.assertIsNone(normalize_orcid("0000-0001-5109-3701"))
        self.assertFalse(is_valid_orcid("0000-0002-1825-0098"))

    def test_a_transposed_pair_is_refused(self):
        """Transposition is the mistake people actually make."""

        self.assertIsNone(normalize_orcid("0000-0002-1852-0097"))

    def test_things_that_are_not_ids_are_refused(self):
        for written in (None, "", "   ", "1234", "abc", "0000-0002-1825-009", "x" * 16):
            with self.subTest(written=written):
                self.assertIsNone(normalize_orcid(written))

    def test_a_lowercase_x_check_digit_is_uppercased(self):
        # `X` is a legal check digit and arrives in either case.
        self.assertEqual(normalize_orcid("0000-0002-1694-233x"), "0000-0002-1694-233X")


if __name__ == "__main__":
    unittest.main()
