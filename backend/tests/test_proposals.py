"""Change proposals: submission, ownership and the decision lifecycle.

What is NOT tested here
-----------------------
Isolation between tenants. It is enforced by row level security, SQLite has no
policies, and the SQLite shim in these tests runs every tenant session against
the same connection -- so a test here would pass for the wrong reason. It is
verified against PostgreSQL in the live end-to-end run recorded in
docs/architecture-v2.md §0.16, where a second tenant saw zero proposals, was
refused the single record with 404, and was refused a withdrawal with 404.

What is tested is the part that holds on any engine: the tenant is taken from the
account and never from the request, the vocabulary and target rules are enforced,
and a proposal that has been decided cannot be decided again.
"""

import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.deps as dependencies
from app.core.security import hash_password
from app.db.models import Tenant, User
from app.db import Base, get_db
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.tenant import router as tenant_router


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        with self.engine.begin() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS control")
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS tenant")

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        self.tenant = Tenant(slug="test-kutuphane", display_name="Test Kütüphanesi")
        self.db.add(self.tenant)
        self.db.flush()

        self.user = User(
            tenant_id=self.tenant.id,
            email="katalog@test.edu.tr",
            display_name="Test Katalog",
            password_hash=hash_password("parola-12345"),
            role="librarian",
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(self.user)
        self.db.commit()

        self._original_tenant_session = dependencies.tenant_session
        test_session = self.db

        @contextmanager
        def _tenant_session(_tenant_id):
            yield test_session

        dependencies.tenant_session = _tenant_session

        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(tenant_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

        token = self.client.post(
            "/auth/login",
            json={"email": "katalog@test.edu.tr", "password": "parola-12345"},
        ).json()["token"]

        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        dependencies.tenant_session = self._original_tenant_session
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def submit(self, **overrides):
        body = {
            "change_type": "correction",
            "target_entity_type": "work",
            "target_entity_id": str(uuid4()),
            "field_changes": [
                {
                    "field": "description",
                    "current": "eski",
                    "proposed": "yeni",
                }
            ],
            "rationale": "Aciklama katalog kaydiyla uyusmuyor.",
            "evidence": "Ic kontrol notu 2026/14",
        }
        body.update(overrides)

        return self.client.post(
            "/tenant/proposals",
            json=body,
            headers=self.headers,
        )

    # --------------------------------------------------------------- access

    def test_submission_requires_a_session(self):
        response = self.client.post(
            "/tenant/proposals",
            json={
                "rationale": "yeterince uzun bir gerekce",
                "target_entity_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_listing_requires_a_session(self):
        self.assertEqual(self.client.get("/tenant/proposals").status_code, 401)

    # ----------------------------------------------------------- submission

    def test_proposal_is_created_pending_for_the_callers_tenant(self):
        response = self.submit()

        self.assertEqual(response.status_code, 201, response.text)

        body = response.json()

        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["change_type"], "correction")

        # The tenant comes from the account. There is no field for it in the
        # request, and this asserts the stored value is the account's.
        self.assertEqual(body["tenant_id"], str(self.tenant.id))
        self.assertEqual(body["submitted_by_email"], "katalog@test.edu.tr")

    def test_a_tenant_id_in_the_body_is_not_honoured(self):
        other = Tenant(slug="baska", display_name="Başka Kütüphane")
        self.db.add(other)
        self.db.commit()

        response = self.submit(tenant_id=str(other.id))

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["tenant_id"], str(self.tenant.id))

    def test_field_changes_round_trip(self):
        response = self.submit()

        changes = response.json()["field_changes"]

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "description")
        self.assertEqual(changes[0]["current"], "eski")
        self.assertEqual(changes[0]["proposed"], "yeni")

    def test_short_rationale_is_refused(self):
        self.assertEqual(self.submit(rationale="kisa").status_code, 422)

    # -------------------------------------------------------------- vocabulary

    def test_unknown_change_type_is_refused(self):
        response = self.submit(change_type="uydurma")

        # The vocabulary is a check constraint, so the engine decides. SQLite
        # gives no SQLSTATE, which is why the answer is allowed to be either the
        # translated 409 or the database-level 422.
        self.assertIn(response.status_code, (409, 422), response.text)

    def test_a_correction_must_name_its_target(self):
        response = self.submit(target_entity_id=None)

        self.assertIn(response.status_code, (409, 422), response.text)

    def test_an_addition_must_not_name_a_target(self):
        response = self.submit(
            change_type="addition",
            target_entity_id=str(uuid4()),
        )

        self.assertIn(response.status_code, (409, 422), response.text)

    def test_an_addition_without_a_target_is_accepted(self):
        response = self.submit(change_type="addition", target_entity_id=None)

        self.assertEqual(response.status_code, 201, response.text)

    # ------------------------------------------------------------- lifecycle

    def test_listing_returns_own_proposals(self):
        self.submit()

        response = self.client.get("/tenant/proposals", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 1)

    def test_filtering_by_status(self):
        self.submit()

        pending = self.client.get(
            "/tenant/proposals?status=pending", headers=self.headers
        )
        applied = self.client.get(
            "/tenant/proposals?status=applied", headers=self.headers
        )

        self.assertEqual(pending.json()["count"], 1)
        self.assertEqual(applied.json()["count"], 0)

    def test_a_single_proposal_can_be_read(self):
        proposal_id = self.submit().json()["id"]

        response = self.client.get(
            f"/tenant/proposals/{proposal_id}", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], proposal_id)

    def test_unknown_proposal_is_not_found(self):
        response = self.client.get(
            f"/tenant/proposals/{uuid4()}", headers=self.headers
        )

        self.assertEqual(response.status_code, 404)

    def test_pending_proposal_can_be_withdrawn(self):
        proposal_id = self.submit().json()["id"]

        response = self.client.post(
            f"/tenant/proposals/{proposal_id}/withdraw",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "withdrawn")

    def test_a_withdrawn_proposal_cannot_be_withdrawn_again(self):
        proposal_id = self.submit().json()["id"]

        self.client.post(
            f"/tenant/proposals/{proposal_id}/withdraw", headers=self.headers
        )

        again = self.client.post(
            f"/tenant/proposals/{proposal_id}/withdraw",
            headers=self.headers,
        )

        # A decision is a record; it does not move back to pending.
        self.assertEqual(again.status_code, 404)


if __name__ == "__main__":
    unittest.main()
