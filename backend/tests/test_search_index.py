from __future__ import annotations

import unittest
import uuid

from app.services.search_index import decode_cursor, encode_cursor


class SearchCursorTests(unittest.TestCase):
    def test_cursor_round_trips_score_and_work_id(self):
        work_id = uuid.uuid4()

        cursor = encode_cursor(0.8125, work_id, "query-context")

        self.assertEqual(
            decode_cursor(cursor, "query-context"),
            (0.8125, work_id),
        )

    def test_cursor_cannot_be_reused_for_another_query_or_filter_set(self):
        cursor = encode_cursor(0.5, uuid.uuid4(), "context-one")

        with self.assertRaisesRegex(ValueError, "does not match"):
            decode_cursor(cursor, "context-two")

    def test_malformed_cursor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid search cursor"):
            decode_cursor("not-a-cursor", "query-context")

    def test_non_finite_score_is_rejected(self):
        cursor = encode_cursor(float("nan"), uuid.uuid4(), "query-context")

        with self.assertRaisesRegex(ValueError, "score"):
            decode_cursor(cursor, "query-context")


if __name__ == "__main__":
    unittest.main()