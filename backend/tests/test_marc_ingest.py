from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.core.marc_mapping import MappedRecord, NormalizedCode
from app.services import marc_ingest


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar(self):
        return self.value


class _Executor:
    def __init__(self):
        self.source_ids = {}
        self.marc_identifiers = {}
        self.work_manifestations = {}

    def execute(self, statement, parameters=None):
        sql = str(statement).lower()
        parameters = parameters or {}

        if "select id from public.source_systems where code" in sql:
            source_id = self.source_ids.get(parameters["code"])
            return _Result(source_id)

        if "insert into public.source_systems" in sql:
            self.source_ids[parameters["code"]] = parameters["id"]
            return _Result()

        if "select em.manifestation_entity_id from public.works" in sql:
            identifier = parameters["value"]
            found = self.marc_identifiers.get(identifier)
            return _Result(found)

        if "insert into public.identifiers" in sql and "'marc'" in sql:
            self.marc_identifiers[parameters["value"]] = self.work_manifestations[
                parameters["entity"]
            ]

        return _Result()


class MarcIngestIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.executor = _Executor()
        self.mapped = MappedRecord(
            control_number="LOCAL-001",
            title="A title",
            library_code=NormalizedCode(raw="BR-1", normalized="BR-1"),
        )

    def ingest(self, source_code):
        def write_record(executor, mapped):
            work_id = uuid.uuid4()
            manifestation_id = uuid.uuid4()
            executor.work_manifestations[work_id] = manifestation_id
            return {
                "work_entity_id": work_id,
                "manifestation_entity_id": manifestation_id,
            }

        with (
            patch.object(marc_ingest, "parse_records", return_value=iter([object()])),
            patch.object(marc_ingest, "map_record", return_value=self.mapped),
            patch.object(
                marc_ingest,
                "_write_record",
                side_effect=write_record,
            ) as write_record_mock,
            patch.object(marc_ingest, "_write_holding", return_value=None) as write_holding_mock,
        ):
            result = marc_ingest.ingest(
                self.executor,
                b"record",
                source_code=source_code,
                source_name=source_code,
            )

        return result, write_record_mock.call_count, write_holding_mock.call_count

    def test_reimport_from_same_source_is_unchanged(self):
        first, first_writes, first_holding_attempts = self.ingest("marc:library-a")
        second, second_writes, second_holding_attempts = self.ingest("marc:library-a")

        self.assertEqual(first["created"], 1)
        self.assertEqual(first_writes, 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(second_writes, 0)
        self.assertEqual(first_holding_attempts, 1)
        self.assertEqual(second_holding_attempts, 1)

    def test_same_local_control_number_from_another_source_is_imported(self):
        first, _, _ = self.ingest("marc:library-a")
        second, second_writes, _ = self.ingest("marc:library-b")

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 1)
        self.assertEqual(second["unchanged"], 0)
        self.assertEqual(second_writes, 1)
        self.assertEqual(len(self.executor.marc_identifiers), 2)


if __name__ == "__main__":
    unittest.main()