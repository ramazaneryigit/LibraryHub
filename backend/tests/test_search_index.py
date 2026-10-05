from __future__ import annotations

import unittest
import uuid

from app.api.v1.routes.search import _merge_duplicate_work_details
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


class SearchDuplicateWorkMergeTests(unittest.TestCase):
    def test_same_title_and_author_records_are_merged(self):
        left = {
            "entity_id": "work-1",
            "canonical_title": "Suç ve Ceza",
            "original_title": None,
            "authors": [
                {"entity_id": "author-1", "name": "Fyodor Dostoyevski", "role": "author"},
                {"entity_id": "translator-1", "name": "Mazlum Beyhan", "role": "çeviren"},
            ],
            "subjects": [],
            "expressions": [{
                "entity_id": "expression-1",
                "manifestations": [{
                    "entity_id": "manifestation-1",
                    "publication_date": "2024",
                    "holdings": [{"entity_id": "lib-1", "name": "A Kütüphane"}],
                }],
            }],
        }
        right = {
            "entity_id": "work-2",
            "canonical_title": "Suç ve Ceza",
            "original_title": None,
            "authors": [{"entity_id": "author-2", "name": "Dostoyevski, Fyodor", "role": "author"}],
            "subjects": [],
            "expressions": [{
                "entity_id": "expression-2",
                "manifestations": [{
                    "entity_id": "manifestation-2",
                    "publication_date": "2025",
                    "holdings": [{"entity_id": "lib-2", "name": "B Kütüphane"}],
                }],
            }],
        }

        merged = _merge_duplicate_work_details([left, right])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["entity_id"], "work-1")
        self.assertEqual(len(merged[0]["expressions"]), 2)
        self.assertEqual(
            {m["entity_id"] for expr in merged[0]["expressions"] for m in expr["manifestations"]},
            {"manifestation-1", "manifestation-2"},
        )


if __name__ == "__main__":
    unittest.main()