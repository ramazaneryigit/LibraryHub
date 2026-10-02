from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import authority_queue


class _Result:
    def mappings(self):
        return self

    def all(self):
        return []


class _Executor:
    def __init__(self):
        self.statement = None
        self.parameters = None

    def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters
        return _Result()


class AuthorityTypeScopeTests(unittest.TestCase):
    def test_publisher_candidates_only_include_publishers(self):
        executor = _Executor()

        authority_queue.find_existing(
            executor,
            "Anadolu Yayınları",
            agent_type="publisher",
        )

        self.assertIn("from public.collective_agents ca", executor.statement)
        self.assertIn("ca.agent_type = :agent_type", executor.statement)
        self.assertNotIn("public.persons", executor.statement)
        self.assertEqual(executor.parameters["agent_type"], "publisher")

    def test_person_candidates_do_not_include_collective_agents(self):
        executor = _Executor()

        authority_queue.find_existing(
            executor,
            "Ayşe Yılmaz",
            agent_type="person",
        )

        self.assertIn("from public.persons p", executor.statement)
        self.assertNotIn("public.collective_agents", executor.statement)

    def test_resolver_passes_the_incoming_agent_type_to_candidate_lookup(self):
        executor = _Executor()

        with (
            patch.object(authority_queue, "find_existing", return_value=[]) as lookup,
            patch("app.core.authority.suggest", return_value=[]),
        ):
            resolved, queued = authority_queue.resolve_agent(
                executor,
                "Anadolu Yayınları",
                "publisher",
            )

        lookup.assert_called_once_with(
            executor,
            "Anadolu Yayınları",
            agent_type="publisher",
        )
        self.assertIsNone(resolved)
        self.assertFalse(queued)


if __name__ == "__main__":
    unittest.main()