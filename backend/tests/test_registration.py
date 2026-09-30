"""Self-registration, domain rules and email verification.

The token is read back out of the application log rather than from the database,
which is deliberate: only the SHA-256 of it is stored, so a test that could
recover it from a row would mean the storage was wrong. Capturing the log also
exercises the delivery path, which is the part that will be replaced when a real
mail sender exists.

Anything that depends on PostgreSQL -- the insert guard on `control.users`, and
the fact that a tenant transaction cannot write to the global plane -- is not
here. Row level security and role grants do not exist on SQLite, so such a test
would pass for the wrong reason. Those are covered by `scripts/run_scale_checks.py`
against the real engine.
"""

import logging
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import hash_session_token
from app.db.models import (
    Branch,
    EmailVerification,
    Organization,
    OrganizationDomain,
    Tenant,
    User,
)
from app.db import Base, get_db
from app.email_domains import CORPORATE, INSTITUTIONAL, classify_email, domain_of
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.tenant import router as tenant_router


class DomainRuleTests(unittest.TestCase):
    def test_academic_domains_are_institutional(self):
        for address in (
            "katalog@kku.edu.tr",
            "hoca@metu.edu.tr",
            "x@harvard.edu",
            "y@ox.ac.uk",
            "z@sub.kku.edu.tr",
        ):
            kind, _ = classify_email(address)
            self.assertEqual(kind, INSTITUTIONAL, address)

    def test_other_domains_are_corporate(self):
        for address in (
            "a@yayinevi.com.tr",
            "b@ornek.com",
            # Ends with "edu" but is not an academic suffix: the comparison is on
            # domain boundaries, not on substrings.
            "c@myedu.com",
            "d@edutr.com.tr",
        ):
            kind, _ = classify_email(address)
            self.assertEqual(kind, CORPORATE, address)

    def test_free_mail_is_refused_with_a_reason(self):
        for address in ("a@gmail.com", "b@hotmail.com", "c@yahoo.com.tr"):
            kind, reason = classify_email(address)
            self.assertIsNone(kind, address)
            self.assertIn("Ücretsiz", reason)

    def test_unusable_addresses_are_refused(self):
        for address in ("", "yok", "@", "a@", "a@b", "a b@c.com"):
            kind, _ = classify_email(address)
            self.assertIsNone(kind, address)

    def test_domain_is_normalised(self):
        self.assertEqual(domain_of("X@K.K.U.EDU.TR"), "k.k.u.edu.tr")
        self.assertEqual(domain_of("a@kku.edu.tr."), "kku.edu.tr")


class _VerificationCapture(logging.Handler):
    """Collects the delivered verification links."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())

    def latest_token(self):
        for message in reversed(self.messages):
            if "token=" in message:
                return message.split("token=")[1].split(" ")[0]

        raise AssertionError("no verification link was delivered")


class RegistrationTests(unittest.TestCase):
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

        self.organization = Organization(
            tenant_id=self.tenant.id,
            name="Test Üniversitesi",
        )
        self.db.add(self.organization)
        self.db.flush()

        self.db.add(
            OrganizationDomain(
                domain="test.edu.tr",
                organization_id=self.organization.id,
                verified_at=datetime.now(timezone.utc),
                verification_method="academic_domain",
            )
        )
        self.db.add(
            OrganizationDomain(
                domain="testyayinevi.com.tr",
                organization_id=self.organization.id,
                verified_at=datetime.now(timezone.utc),
                verification_method="dns_txt",
            )
        )
        self.db.commit()

        self.capture = _VerificationCapture()
        self.auth_logger = logging.getLogger("libraryhub.auth")
        self.auth_logger.addHandler(self.capture)

        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(tenant_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.auth_logger.removeHandler(self.capture)
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def register(self, email, password="parola-12345", name="Yeni Kullanıcı"):
        return self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "display_name": name},
        )

    def login(self, email, password="parola-12345"):
        return self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

    # ------------------------------------------------------------ refusals

    def test_free_mail_address_is_refused(self):
        response = self.register("biri@gmail.com")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Ücretsiz", response.json()["detail"])

    def test_unmapped_domain_is_refused(self):
        response = self.register("hoca@baskabiruni.edu.tr")

        self.assertEqual(response.status_code, 403)
        self.assertIn("tanımlı değil", response.json()["detail"])

    # --------------------------------------------------------- registration

    def test_academic_address_registers_as_institutional(self):
        response = self.register("hoca@test.edu.tr")

        self.assertEqual(response.status_code, 202, response.text)

        body = response.json()

        self.assertEqual(body["account_kind"], INSTITUTIONAL)
        self.assertEqual(body["organization"], "Test Üniversitesi")

        user = self.db.query(User).filter_by(email="hoca@test.edu.tr").one()

        # Created, attached to the organization's tenant, and not yet usable.
        self.assertEqual(user.tenant_id, self.tenant.id)
        self.assertIsNone(user.email_verified_at)
        self.assertEqual(user.role, "librarian")

    def test_corporate_address_registers_as_corporate(self):
        response = self.register("sorumlu@testyayinevi.com.tr")

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["account_kind"], CORPORATE)

    def test_registration_does_not_return_the_token(self):
        response = self.register("hoca@test.edu.tr")

        # Handing the token back to the caller would defeat the check.
        self.assertNotIn("token", response.json())

    def test_password_is_hashed_not_stored(self):
        self.register("hoca@test.edu.tr")

        user = self.db.query(User).filter_by(email="hoca@test.edu.tr").one()

        self.assertNotIn("parola-12345", user.password_hash)
        self.assertTrue(user.password_hash.startswith("scrypt$"))

    def test_retrying_a_pending_registration_replaces_it(self):
        self.register("hoca@test.edu.tr")
        first = self.db.query(User).filter_by(email="hoca@test.edu.tr").one()

        response = self.register("hoca@test.edu.tr", name="Düzeltilmiş Ad")

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.db.query(User).filter_by(email="hoca@test.edu.tr").count(), 1)
        self.assertNotEqual(
            self.db.query(User).filter_by(email="hoca@test.edu.tr").one().id,
            first.id,
        )

    def test_registering_an_already_verified_address_is_refused(self):
        self.register("hoca@test.edu.tr")
        self.verify(self.capture.latest_token())

        self.assertEqual(self.register("hoca@test.edu.tr").status_code, 409)

    # --------------------------------------------------------- verification

    def verify(self, token):
        return self.client.post("/auth/verify-email", json={"token": token})

    def test_login_is_refused_until_the_address_is_verified(self):
        self.register("hoca@test.edu.tr")

        response = self.login("hoca@test.edu.tr")

        self.assertEqual(response.status_code, 403)
        self.assertIn("doğrulanmam", response.json()["detail"])

    def test_verification_makes_the_account_usable(self):
        self.register("hoca@test.edu.tr")

        token = self.capture.latest_token()
        response = self.verify(token)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "verified")
        self.assertEqual(self.login("hoca@test.edu.tr").status_code, 200)

    def test_a_token_cannot_be_used_twice(self):
        self.register("hoca@test.edu.tr")
        token = self.capture.latest_token()

        self.assertEqual(self.verify(token).status_code, 200)
        self.assertEqual(self.verify(token).status_code, 400)

    def test_expired_token_is_refused(self):
        self.register("hoca@test.edu.tr")
        token = self.capture.latest_token()

        verification = self.db.query(EmailVerification).one()
        verification.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.db.commit()

        self.assertEqual(self.verify(token).status_code, 400)

    def test_unknown_token_is_refused(self):
        self.assertEqual(self.verify("bu-token-yok").status_code, 400)

    def test_only_the_hash_is_stored(self):
        self.register("hoca@test.edu.tr")
        token = self.capture.latest_token()

        verification = self.db.query(EmailVerification).one()

        self.assertNotEqual(verification.token_hash, token)
        self.assertEqual(verification.token_hash, hash_session_token(token))

    def test_resending_consumes_the_previous_token(self):
        self.register("hoca@test.edu.tr")
        first = self.capture.latest_token()

        self.client.post(
            "/auth/resend-verification",
            json={"email": "hoca@test.edu.tr"},
        )
        second = self.capture.latest_token()

        self.assertNotEqual(first, second)
        self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_resending_for_an_unknown_address_says_nothing(self):
        response = self.client.post(
            "/auth/resend-verification",
            json={"email": "yok@test.edu.tr"},
        )

        # Same answer as a real address, so it cannot be used to test which
        # addresses are registered.
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "verification_sent"})


if __name__ == "__main__":
    unittest.main()
