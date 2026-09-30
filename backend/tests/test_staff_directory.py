"""Institution and staff management.

Isolated SQLite; no application database is used. The guard trigger on
`control.users` is PostgreSQL's and is NOT exercised here -- `run_scale_checks.py`
attempts the two escalations against the real database instead. What these tests
cover is the layer above it: the authorization on the routes, the rules the
service applies before any statement runs, and the side effects that would
otherwise be left out.

There is one deliberate gap. A test asserting that an administrator account
cannot be promoted *by the database* would pass here for the wrong reason, since
nothing would refuse it. The assertion is on the service's refusal, and the
trigger is what closes the hole on the real thing.
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

from app.api.v1.routes.admin import router
from app.core.ids import uuid7
from app.core.security import hash_password, hash_session_token, new_session_token
from app.db import Base, get_db
from app.db.models import Tenant, User, UserSession


class StaffDirectoryTests(unittest.TestCase):
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

        self.admin_user, self.admin = self._account(
            tenant_id=None,
            email="platform@libraryhub.local",
            role="admin",
        )

        self.librarian_user, self.librarian = self._account(
            tenant_id=self.kku.id,
            email="katalog@kku.edu.tr",
            role="librarian",
        )

        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------- helpers

    def _account(self, tenant_id, email, role):
        """Returns the account and a live session token for it."""

        user = User(
            id=uuid7(),
            tenant_id=tenant_id,
            email=email,
            display_name=email,
            password_hash=hash_password("parola-12345"),
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
                expires_at=datetime(
                    datetime.now(timezone.utc).year + 1, 1, 1, tzinfo=timezone.utc
                ),
            )
        )

        return user, token

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------- authorization

    def test_the_endpoints_require_a_session(self):
        for path in ("/admin/tenants", "/admin/users"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_a_librarian_is_refused(self):
        for path in ("/admin/tenants", "/admin/users"):
            response = self.client.get(path, headers=self._headers(self.librarian))
            self.assertEqual(response.status_code, 403, path)

    # -------------------------------------------------------- institutions

    def test_institutions_are_listed_with_their_staff_counts(self):
        response = self.client.get(
            "/admin/tenants",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 200, response.text)

        tenants = {row["slug"]: row for row in response.json()["tenants"]}

        self.assertEqual(set(tenants), {"kku", "hacettepe"})
        self.assertEqual(tenants["kku"]["staff_count"], 1)
        self.assertEqual(tenants["hacettepe"]["staff_count"], 0)

    def test_an_unknown_institution_is_a_404(self):
        response = self.client.get(
            f"/admin/tenants/{uuid.uuid4()}",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 404, response.text)

    # ------------------------------------------------------------- reading

    def test_platform_accounts_are_visible_and_marked(self):
        response = self.client.get(
            "/admin/users",
            headers=self._headers(self.admin),
        )

        body = response.json()

        self.assertEqual(body["count"], 2)

        platform = next(
            row for row in body["accounts"] if row["role"] == "admin"
        )

        self.assertIsNone(platform["tenant_id"])
        self.assertIsNone(platform["tenant_name"])

    def test_platform_accounts_can_be_left_out(self):
        response = self.client.get(
            "/admin/users?include_platform=false",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            response.json()["accounts"][0]["email"],
            "katalog@kku.edu.tr",
        )

    def test_an_unknown_role_filter_is_refused(self):
        response = self.client.get(
            "/admin/users?role=patron",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 400, response.text)

    # ------------------------------------------------------------ creating

    def test_an_account_is_created_unverified(self):
        """The holder has to confirm the address, and cannot log in until then.

        The guard trigger refuses an application role an account that is already
        verified; this asserts the shape that leaves behind.
        """

        response = self.client.post(
            "/admin/users",
            headers=self._headers(self.admin),
            json={
                "tenant_id": str(self.kku.id),
                "email": "Yeni.Kutuphaneci@KKU.edu.tr",
                "display_name": "Yeni Kütüphaneci",
                "role": "librarian",
                "password": "yeni-parola-123",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)

        body = response.json()

        self.assertEqual(body["email"], "yeni.kutuphaneci@kku.edu.tr")
        self.assertIsNone(body["email_verified_at"])
        self.assertEqual(body["account_kind"], "institutional")
        self.assertTrue(body["is_active"])

    def test_an_administrator_role_cannot_be_requested(self):
        response = self.client.post(
            "/admin/users",
            headers=self._headers(self.admin),
            json={
                "tenant_id": str(self.kku.id),
                "email": "olmamali@kku.edu.tr",
                "display_name": "Olmamalı",
                "role": "admin",
                "password": "olmamali-parola",
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_a_duplicate_address_is_a_conflict(self):
        payload = {
            "tenant_id": str(self.kku.id),
            "email": "katalog@kku.edu.tr",
            "display_name": "Kopya",
            "role": "librarian",
            "password": "kopya-parola-1",
        }

        response = self.client.post(
            "/admin/users",
            headers=self._headers(self.admin),
            json=payload,
        )

        self.assertEqual(response.status_code, 409, response.text)

    # ------------------------------------------------------------ updating

    def test_an_ordinary_account_can_be_changed(self):
        target = self.db.query(User).filter(User.email == "katalog@kku.edu.tr").one()

        response = self.client.patch(
            f"/admin/users/{target.id}",
            headers=self._headers(self.admin),
            json={"display_name": "Katalog Sorumlusu", "role": "viewer"},
        )

        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()

        self.assertEqual(body["display_name"], "Katalog Sorumlusu")
        self.assertEqual(body["role"], "viewer")

    def test_an_administrator_account_cannot_be_touched(self):
        """The rule the trigger enforces, checked before the statement runs."""

        response = self.client.patch(
            f"/admin/users/{self.admin_user.id}",
            headers=self._headers(self.admin),
            json={"display_name": "Ele Geçir"},
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("create_user.py", response.json()["detail"])

    def test_an_administrator_password_cannot_be_reset(self):
        response = self.client.post(
            f"/admin/users/{self.admin_user.id}/password",
            headers=self._headers(self.admin),
            json={"password": "ele-gecirme-parolasi"},
        )

        self.assertEqual(response.status_code, 403, response.text)

    def test_deactivating_ends_the_live_sessions(self):
        """An account switched off while its session keeps working is not off."""

        target = self.db.query(User).filter(User.email == "katalog@kku.edu.tr").one()

        before = (
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == target.id,
                UserSession.revoked_at.is_(None),
            )
            .count()
        )

        self.assertEqual(before, 1)

        response = self.client.patch(
            f"/admin/users/{target.id}",
            headers=self._headers(self.admin),
            json={"is_active": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["is_active"])

        after = (
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == target.id,
                UserSession.revoked_at.is_(None),
            )
            .count()
        )

        self.assertEqual(after, 0)

    def test_a_password_reset_ends_the_old_sessions(self):
        """Otherwise the holder of the old session is still in."""

        target = self.db.query(User).filter(User.email == "katalog@kku.edu.tr").one()

        response = self.client.post(
            f"/admin/users/{target.id}/password",
            headers=self._headers(self.admin),
            json={"password": "bambaska-parola"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["revoked_sessions"], 1)

    def test_sessions_can_be_ended_on_their_own(self):
        target = self.db.query(User).filter(User.email == "katalog@kku.edu.tr").one()

        response = self.client.post(
            f"/admin/users/{target.id}/sessions/revoke",
            headers=self._headers(self.admin),
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["revoked_sessions"], 1)

        again = self.client.post(
            f"/admin/users/{target.id}/sessions/revoke",
            headers=self._headers(self.admin),
        )

        self.assertEqual(again.json()["revoked_sessions"], 0)

    def test_an_unknown_account_is_a_404(self):
        missing = uuid.uuid4()

        for method, path in (
            ("get", f"/admin/users/{missing}"),
            ("patch", f"/admin/users/{missing}"),
            ("post", f"/admin/users/{missing}/password"),
            ("post", f"/admin/users/{missing}/sessions/revoke"),
        ):
            body = {}

            if method == "patch":
                body = {"display_name": "Yeterince Uzun"}
            elif path.endswith("password"):
                body = {"password": "yeterince-uzun"}

            response = getattr(self.client, method)(
                path,
                headers=self._headers(self.admin),
                **({"json": body} if body else {}),
            )

            self.assertEqual(response.status_code, 404, f"{method} {path}")


if __name__ == "__main__":
    unittest.main()
