"""The curation endpoints: who may reach them, and what applying actually writes.

These run on the owner credential, because `tenant.change_proposals` is covered
by row level security and a reviewer has no tenant to bind. That makes the
authorization on these routes load-bearing rather than decorative, so it is
asserted first.

Isolated SQLite; no application database is used. Row level security is a
PostgreSQL feature and is not exercised here -- what these tests check is the
wiring above it and the rules in `app/services/proposal_review.py`.
"""

import os
import unittest
import uuid
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import owner_db
from app.api.v1.routes.admin import router
from app.core.ids import uuid7
from app.core.security import hash_password, hash_session_token, new_session_token
from app.db import Base, get_db
from app.db.models import (
    Entity,
    Tenant,
    TenantChangeProposal,
    User,
    UserSession,
    Work,
)


class CurationTests(unittest.TestCase):
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

        self.kku = Tenant(slug="kku", display_name="Kırıkkale Üniversitesi")
        self.hacettepe = Tenant(slug="hacettepe", display_name="Hacettepe")

        self.db.add_all([self.kku, self.hacettepe])
        self.db.flush()

        # A platform administrator: no tenant, which is what lets them read every
        # institution's proposals at once.
        self.admin = self._account(
            tenant_id=None,
            email="platform@libraryhub.local",
            role="admin",
        )

        # And an ordinary librarian, who must not get anywhere near these routes.
        self.librarian = self._account(
            tenant_id=self.kku.id,
            email="katalog@kku.edu.tr",
            role="librarian",
        )

        self.work_id = uuid7()

        self.db.add(Entity(id=self.work_id, entity_type="WORK"))
        self.db.add(
            Work(
                entity_id=self.work_id,
                canonical_title="Bilgi Yönetimi",
                original_language="tr",
            )
        )

        self.proposal_id = self._proposal(
            tenant_id=self.kku.id,
            changes=[
                {"field": "original_title", "current": None, "proposed": "Yeni"},
                # Not on the whitelist, and must be reported rather than written.
                {"field": "canonical_title", "current": "a", "proposed": "b"},
            ],
        )

        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[owner_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------- helpers

    def _account(self, tenant_id, email, role):
        user = User(
            tenant_id=tenant_id,
            email=email,
            display_name=email,
            password_hash=hash_password("parola-123"),
            role=role,
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        self.db.flush()

        token = new_session_token()

        self.db.add(
            UserSession(
                id=uuid7(),
                user_id=user.id,
                token_hash=hash_session_token(token),
                expires_at=datetime.now(timezone.utc).replace(
                    year=datetime.now(timezone.utc).year + 1
                ),
            )
        )

        return token

    def _proposal(self, tenant_id, changes, change_type="correction"):
        proposal = TenantChangeProposal(
            id=uuid7(),
            tenant_id=tenant_id,
            submitted_by_email="katalog@kku.edu.tr",
            change_type=change_type,
            target_entity_type=(
                "work" if change_type != "addition" else None
            ),
            target_entity_id=(
                self.work_id if change_type != "addition" else None
            ),
            field_changes=changes,
            rationale="Sınama gerekçesi, en az on karakter.",
            evidence="Sınama kaynağı",
        )
        self.db.add(proposal)
        self.db.flush()

        return proposal.id

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    # -------------------------------------------------------- authorization

    def test_the_endpoints_require_a_session(self):
        for path in ("/admin/proposals", "/admin/proposals/summary"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_a_librarian_is_refused(self):
        response = self.client.get(
            "/admin/proposals",
            headers=self._headers(self.librarian),
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("admin", response.json()["detail"])

    def test_an_administrator_is_answered(self):
        response = self.client.get(
            "/admin/proposals",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 1)

    # -------------------------------------------------------------- reading

    def test_proposals_from_every_tenant_are_visible(self):
        """The reason these routes need the owner credential.

        A tenant transaction sees its own rows and nothing else. A reviewer sees
        all of them, or there is no review.
        """

        self._proposal(
            tenant_id=self.hacettepe.id,
            changes=[
                {"field": "original_language", "current": "tr", "proposed": "en"}
            ],
        )
        self.db.commit()

        response = self.client.get(
            "/admin/proposals",
            headers=self._headers(self.admin),
        )

        tenants = {row["tenant_name"] for row in response.json()["proposals"]}

        self.assertEqual(
            tenants,
            {"Kırıkkale Üniversitesi", "Hacettepe"},
        )

    def test_an_unknown_status_is_refused(self):
        response = self.client.get(
            "/admin/proposals?status=saçma",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 400, response.text)

    def test_the_summary_counts_by_status(self):
        self._proposal(
            tenant_id=self.kku.id,
            changes=[{"field": "extent", "current": None, "proposed": "1 cilt"}],
        )
        self.db.commit()

        response = self.client.get(
            "/admin/proposals/summary",
            headers=self._headers(self.admin),
        )

        body = response.json()

        self.assertEqual(body["total"], 2)
        self.assertEqual(body["waiting"], 2)
        self.assertEqual(body["counts"]["pending"], 2)

    # ------------------------------------------------------------ deciding

    def test_a_decision_records_the_authenticated_account(self):
        """Not a name the caller supplied.

        Until these endpoints existed the reviewer was a string typed on a
        command line, which records a claim rather than an identity.
        """

        response = self.client.post(
            f"/admin/proposals/{self.proposal_id}/decision",
            headers=self._headers(self.admin),
            json={"decision": "accepted", "note": "Kaynak doğrulandı"},
        )

        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()

        self.assertEqual(body["status"], "accepted")
        self.assertEqual(body["reviewed_by"], "platform@libraryhub.local")
        self.assertEqual(body["review_note"], "Kaynak doğrulandı")
        self.assertIsNotNone(body["reviewed_at"])

    def test_only_a_pending_proposal_can_be_decided(self):
        headers = self._headers(self.admin)

        self.client.post(
            f"/admin/proposals/{self.proposal_id}/decision",
            headers=headers,
            json={"decision": "accepted"},
        )

        again = self.client.post(
            f"/admin/proposals/{self.proposal_id}/decision",
            headers=headers,
            json={"decision": "rejected"},
        )

        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("accepted", again.json()["detail"])

    def test_an_unknown_proposal_is_a_404(self):
        response = self.client.post(
            f"/admin/proposals/{uuid.uuid4()}/decision",
            headers=self._headers(self.admin),
            json={"decision": "accepted"},
        )

        self.assertEqual(response.status_code, 404, response.text)

    def test_a_nonsense_decision_is_refused(self):
        response = self.client.post(
            f"/admin/proposals/{self.proposal_id}/decision",
            headers=self._headers(self.admin),
            json={"decision": "belki"},
        )

        self.assertEqual(response.status_code, 422, response.text)

    # ------------------------------------------------------------ applying

    def test_a_pending_proposal_cannot_be_applied(self):
        response = self.client.post(
            f"/admin/proposals/{self.proposal_id}/apply",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("pending", response.json()["detail"])

    def test_applying_writes_the_whitelist_and_reports_the_rest(self):
        """A field outside the whitelist is dropped, and that has to be visible.

        `canonical_title` is on the whitelist for Work -- so to make the drop
        observable the proposal asks for a field that genuinely is not, and the
        assertion is about what the response admits to.
        """

        headers = self._headers(self.admin)

        proposal_id = self._proposal(
            tenant_id=self.kku.id,
            changes=[
                {"field": "original_title", "proposed": "Özgün"},
                # The identity registry is not reachable this way.
                {"field": "entity_type", "proposed": "PERSON"},
            ],
        )
        self.db.commit()

        self.client.post(
            f"/admin/proposals/{proposal_id}/decision",
            headers=headers,
            json={"decision": "accepted"},
        )

        response = self.client.post(
            f"/admin/proposals/{proposal_id}/apply",
            headers=headers,
        )

        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()

        self.assertEqual(body["applied"], {"original_title": "Özgün"})
        self.assertEqual(body["dropped"], ["entity_type"])
        self.assertEqual(body["proposal"]["status"], "applied")
        self.assertIsNotNone(body["proposal"]["applied_at"])

        self.db.expire_all()

        self.assertEqual(
            self.db.get(Work, self.work_id).original_title,
            "Özgün",
        )

    def test_a_canonical_title_change_also_refreshes_the_normalized_one(self):
        """Otherwise matching silently stops working for the corrected record."""

        proposal_id = self._proposal(
            tenant_id=self.kku.id,
            changes=[
                {
                    "field": "canonical_title",
                    "current": "Bilgi Yönetimi",
                    "proposed": "Bilgi Yönetimi El Kitabı",
                }
            ],
        )
        self.db.commit()

        headers = self._headers(self.admin)

        self.client.post(
            f"/admin/proposals/{proposal_id}/decision",
            headers=headers,
            json={"decision": "accepted"},
        )

        self.client.post(
            f"/admin/proposals/{proposal_id}/apply",
            headers=headers,
        )

        self.db.expire_all()

        work = self.db.get(Work, self.work_id)

        self.assertEqual(work.canonical_title, "Bilgi Yönetimi El Kitabı")
        # Pinned exactly, because the point of the test is that the stored value
        # went through the same normalization as a probe would -- `normalize_text`
        # lowercases and folds most diacritics but keeps the dotless i.
        self.assertEqual(work.normalized_title, "bilgi yonetimi el kitabı")

    def test_an_addition_has_nothing_to_apply(self):
        """An addition names no target, so there is no row to write."""

        proposal_id = self._proposal(
            tenant_id=self.kku.id,
            changes=[{"field": "canonical_title", "proposed": "Yeni Bir Eser"}],
            change_type="addition",
        )
        self.db.commit()

        headers = self._headers(self.admin)

        self.client.post(
            f"/admin/proposals/{proposal_id}/decision",
            headers=headers,
            json={"decision": "accepted"},
        )

        response = self.client.post(
            f"/admin/proposals/{proposal_id}/apply",
            headers=headers,
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("ekleme", response.json()["detail"])

    def test_a_rejected_proposal_cannot_be_applied(self):
        headers = self._headers(self.admin)

        self.client.post(
            f"/admin/proposals/{self.proposal_id}/decision",
            headers=headers,
            json={"decision": "rejected", "note": "Kaynak yetersiz"},
        )

        response = self.client.post(
            f"/admin/proposals/{self.proposal_id}/apply",
            headers=headers,
        )

        self.assertEqual(response.status_code, 409, response.text)


if __name__ == "__main__":
    unittest.main()
