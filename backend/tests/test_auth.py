"""Authentication and tenant-context contract tests.

What is NOT tested here
-----------------------
Isolation. SQLite has no row level security, so "tenant A cannot see tenant B's
rows" cannot be asserted on this engine at all -- the test would pass for the
wrong reason. That half is verified against PostgreSQL, both by
`scripts/run_scale_checks.py` across every tenant and by the live end-to-end
check recorded in docs/architecture-v2.md §0.13.

What IS tested here is everything that must hold regardless of engine: password
hashing, the login/logout lifecycle, revocation, and the refusal to answer a
tenant endpoint without a valid session.
"""

import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.deps as dependencies
from app.core.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.db.models import Tenant, User, UserSession
from app.db import Base, get_db
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.tenant import router as tenant_router


class PasswordTests(unittest.TestCase):
    def test_round_trip(self):
        stored = hash_password("doğru-parola")
        self.assertTrue(verify_password("doğru-parola", stored))
        self.assertFalse(verify_password("yanlış-parola", stored))

    def test_same_password_hashes_differently(self):
        # A shared salt would let one cracked hash break every identical password.
        self.assertNotEqual(hash_password("aynı"), hash_password("aynı"))

    def test_malformed_hash_is_rejected_rather_than_raising(self):
        for broken in ["", "scrypt", "bcrypt$1$2$3$4$5", "scrypt$a$b$c$d$e", None]:
            self.assertFalse(verify_password("x", broken))

    def test_hash_is_self_describing(self):
        stored = hash_password("parola")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertEqual(len(stored.split("$")), 6)

    def test_token_is_stored_only_as_a_hash(self):
        token = new_session_token()
        digest = hash_session_token(token)

        self.assertNotEqual(digest, token)
        self.assertEqual(len(digest), 64)


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )

        with self.engine.begin() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS control")
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS tenant")

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        self.tenant = Tenant(
            slug='test-kutuphane',
            display_name='Test Kütüphanesi',
        )
        self.db.add(self.tenant)
        self.db.flush()

        self.user = User(
            tenant_id=self.tenant.id,
            email='test@ornek.org',
            display_name='Test Kullanıcı',
            password_hash=hash_password('parola-123'),
            role='librarian',
            # Verified, because an unverified account cannot log in at all --
            # that is asserted on its own in test_registration.py.
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(self.user)
        self.db.commit()

        # `tenant_db` opens its own session through app.db; point it at this
        # engine so the tenant endpoint can be exercised here at all.
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

    def tearDown(self):
        dependencies.tenant_session = self._original_tenant_session
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def login(self, email='test@ornek.org', password='parola-123'):
        return self.client.post(
            '/auth/login',
            json={'email': email, 'password': password},
        )

    # ------------------------------------------------------------- login

    def test_login_returns_a_token_and_the_tenant(self):
        response = self.login()

        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()

        self.assertTrue(body['token'])
        self.assertEqual(body['user']['tenant_id'], str(self.tenant.id))
        self.assertEqual(body['user']['tenant_name'], 'Test Kütüphanesi')
        self.assertNotIn('password_hash', body['user'])

    def test_login_is_case_insensitive_on_email(self):
        self.assertEqual(self.login(email='TEST@Ornek.ORG').status_code, 200)

    def test_wrong_password_is_rejected(self):
        response = self.login(password='yanlış')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid email or password')

    def test_unknown_account_gives_the_same_answer_as_a_wrong_password(self):
        # Otherwise the endpoint tells an attacker which addresses exist.
        unknown = self.login(email='yok@ornek.org')
        wrong = self.login(password='yanlış')

        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.json()['detail'], wrong.json()['detail'])

    def test_inactive_account_is_refused(self):
        self.user.is_active = False
        self.db.commit()

        self.assertEqual(self.login().status_code, 403)

    def test_raw_token_is_not_stored(self):
        token = self.login().json()['token']

        stored = self.db.query(UserSession).all()

        self.assertEqual(len(stored), 1)
        self.assertNotEqual(stored[0].token_hash, token)
        self.assertEqual(stored[0].token_hash, hash_session_token(token))

    # ---------------------------------------------------------------- me

    def test_me_requires_a_token(self):
        self.assertEqual(self.client.get('/auth/me').status_code, 401)

    def test_me_rejects_a_nonsense_token(self):
        # ASCII only: HTTP header values cannot carry arbitrary text, and the
        # test client raises rather than sending it.
        response = self.client.get(
            '/auth/me',
            headers={'Authorization': 'Bearer not-a-real-token'},
        )

        self.assertEqual(response.status_code, 401)

    def test_me_returns_the_account(self):
        token = self.login().json()['token']

        response = self.client.get(
            '/auth/me',
            headers={'Authorization': f'Bearer {token}'},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['email'], 'test@ornek.org')

    # ------------------------------------------------------------ logout

    def test_logout_revokes_the_token(self):
        token = self.login().json()['token']
        headers = {'Authorization': f'Bearer {token}'}

        self.assertEqual(
            self.client.post('/auth/logout', headers=headers).status_code,
            200,
        )
        self.assertEqual(
            self.client.get('/auth/me', headers=headers).status_code,
            401,
        )

        # Revoked, not deleted: the row survives so the fact is still answerable.
        self.assertEqual(self.db.query(UserSession).count(), 1)
        self.assertIsNotNone(self.db.query(UserSession).one().revoked_at)

    def test_expired_session_is_refused(self):
        from datetime import datetime, timedelta, timezone

        token = self.login().json()['token']

        session = self.db.query(UserSession).one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.db.commit()

        response = self.client.get(
            '/auth/me',
            headers={'Authorization': f'Bearer {token}'},
        )

        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------ tenant access

    def test_tenant_endpoint_requires_a_session(self):
        self.assertEqual(self.client.get('/tenant/items').status_code, 401)

    def test_tenant_endpoint_answers_with_a_session(self):
        token = self.login().json()['token']

        response = self.client.get(
            '/tenant/items',
            headers={'Authorization': f'Bearer {token}'},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['tenant_id'], str(self.tenant.id))
        self.assertEqual(response.json()['count'], 0)

    # ------------------------------------------- platform administrators

    def _platform_administrator(self):
        """A curator of the shared record, belonging to no library."""

        administrator = User(
            tenant_id=None,
            email='platform@libraryhub.local',
            display_name='Platform Yöneticisi',
            password_hash=hash_password('parola-123'),
            role='admin',
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(administrator)
        self.db.commit()

        return administrator

    def test_platform_administrator_logs_in_without_a_tenant(self):
        self._platform_administrator()

        response = self.client.post(
            '/auth/login',
            json={
                'email': 'platform@libraryhub.local',
                'password': 'parola-123',
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['user']['role'], 'admin')
        self.assertFalse(response.json()['user']['tenant_name'])

    def test_platform_administrator_is_refused_the_tenant_plane(self):
        """The one place the tenant comes from is the account, or nowhere.

        `tenant_db` does not fall back to a default when the account has no
        tenant: choosing one -- any one -- is exactly the vulnerability the
        binding exists to prevent. The administrator's reach is the global plane.
        """

        self._platform_administrator()

        token = self.client.post(
            '/auth/login',
            json={
                'email': 'platform@libraryhub.local',
                'password': 'parola-123',
            },
        ).json()['token']

        response = self.client.get(
            '/tenant/items',
            headers={'Authorization': f'Bearer {token}'},
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn('not attached to a library', response.json()['detail'])

    def test_only_an_admin_may_have_no_tenant(self):
        """A librarian with no library cannot act, so the database forbids it.

        Enforced as a constraint rather than by the account-creation script,
        because the script is not the only thing that can write the table.
        """

        self.db.add(
            User(
                tenant_id=None,
                email='olmamali@ornek.org',
                display_name='Olmamalı',
                password_hash=hash_password('parola-123'),
                role='librarian',
                email_verified_at=datetime.now(timezone.utc),
            )
        )

        with self.assertRaises(IntegrityError) as caught:
            self.db.commit()

        self.db.rollback()

        self.assertIn(
            'ck_users_tenant_required',
            str(caught.exception),
        )


if __name__ == '__main__':
    unittest.main()
