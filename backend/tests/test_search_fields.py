from __future__ import annotations

import unittest
import uuid

from app.services.search_index import MATCHED_WORKS, search_page


class Result:
    def __init__(self, rows=(), scalar_value=0):
        self.rows = list(rows)
        self.scalar_value = scalar_value

    def scalar(self):
        return self.scalar_value

    def mappings(self):
        return self

    def all(self):
        return self.rows


class SearchExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters or {}))
        if "select count(*) from filtered" in sql:
            return Result(scalar_value=2)
        if "select t.id::text as value" in sql:
            return Result([{"value": "tenant-1", "label": "Kırıkkale Üniversitesi", "count": 7}])
        return Result()


class AdvancedSearchTests(unittest.TestCase):
    def test_search_field_and_identifier_scheme_are_bound(self):
        schemes = {
            "isbn": "ISBN",
            "issn": "ISSN",
            "doi": "DOI",
            "orcid": "ORCID",
        }

        for field, scheme in schemes.items():
            with self.subTest(field=field):
                executor = SearchExecutor()
                result = search_page(executor, "9780000000000", search_field=field)
                parameters = executor.calls[0][1]

                self.assertEqual(parameters["search_field"], field)
                self.assertEqual(parameters["identifier_scheme"], scheme)
                self.assertEqual(parameters["raw_pattern"], "%9780000000000%")
                self.assertEqual(result["total"], 2)
                self.assertEqual(result["institutions"][0]["count"], 7)

    def test_supported_fields_have_typed_match_constraints(self):
        for expected in (
            "d.entity_type = 'WORK'",
            "d.entity_type = 'PERSON'",
            "d.entity_type = 'ORGANIZATION'",
            "d.entity_type = 'MANIFESTATION'",
            "upper(i.scheme) = upper(cast(:identifier_scheme as text))",
            "t.display_name ilike :raw_pattern",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, MATCHED_WORKS)

    def test_semantic_candidates_keep_scores_and_field_scope(self):
        executor = SearchExecutor()
        entity_id = uuid.uuid4()

        search_page(
            executor,
            "a novel about migration",
            search_field="title",
            semantic_matches=[{"entity_id": str(entity_id), "score": 0.91}],
        )

        sql, parameters = executor.calls[0]
        self.assertTrue(parameters["semantic_mode"])
        self.assertEqual(parameters["semantic_entity_ids"], [entity_id])
        self.assertEqual(parameters["semantic_scores"], [0.91])
        self.assertIn("candidate.score", sql)
        self.assertIn("d.entity_type = 'WORK'", sql)
    def test_institution_totals_and_query_facets_are_distinct(self):
        executor = SearchExecutor()

        result = search_page(executor, "Dostoyevski", search_field="author")

        self.assertEqual(
            result["institutions"],
            [{"value": "tenant-1", "label": "Kırıkkale Üniversitesi", "count": 7}],
        )
        self.assertTrue(any("select 'library'" in sql for sql, _ in executor.calls))
        self.assertTrue(any("select t.id::text as value" in sql for sql, _ in executor.calls))


if __name__ == "__main__":
    unittest.main()
