from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.assertions import account_source


class _Executor:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=None):
        self.calls.append((str(statement), parameters))
        return SimpleNamespace(scalar=lambda: "source-id")


class AccountSourceTests(unittest.TestCase):
    def test_tenant_staff_resolve_to_their_tenant_source(self):
        executor = _Executor()
        user = SimpleNamespace(principal_kind="tenant_staff", tenant_id="tenant-id")

        self.assertEqual(account_source(executor, user), "source-id")
        self.assertIn("s.code = 'tenant:' || t.slug", executor.calls[0][0])
        self.assertEqual(executor.calls[0][1], {"tenant_id": "tenant-id"})

    def test_platform_admin_resolves_to_platform_source(self):
        executor = _Executor()
        user = SimpleNamespace(principal_kind="platform", tenant_id=None)

        self.assertEqual(account_source(executor, user), "source-id")
        self.assertIn("code = 'platform'", executor.calls[0][0])

    def test_unmapped_principal_does_not_inherit_platform_source(self):
        executor = _Executor()
        user = SimpleNamespace(principal_kind="publisher", tenant_id=None)

        self.assertIsNone(account_source(executor, user))
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()