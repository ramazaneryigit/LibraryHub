"""Tenant-scoped data quality checks."""

import os
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.deps as dependencies
from app.core.ids import uuid7
from app.core.security import hash_password, hash_session_token, new_session_token
from app.db import Base, get_db
from app.db.models import Tenant, TenantHolding, TenantItem, User, UserSession
from app.api.v1.routes.tenant import router as tenant_router


class TenantDataQualityTests(unittest.TestCase):
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
        self.tenant = Tenant(slug="test", display_name="Test Kütüphanesi")
        self.db.add(self.tenant)
        self.db.flush()

        self.user = User(
            tenant_id=self.tenant.id,
            email="test@example.org",
            display_name="Test Kullanıcı",
            password_hash=hash_password("test-password"),
            role="librarian",
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(self.user)
        self.db.flush()
        self.token = new_session_token()
        self.db.add(
            UserSession(
                id=uuid7(),
                user_id=self.user.id,
                token_hash=hash_session_token(self.token),
                expires_at=datetime(
                    datetime.now(timezone.utc).year + 1, 1, 1, tzinfo=timezone.utc
                ),
            )
        )

        self.empty_holding = self._holding("EMPTY-1")
        self.item_holding = self._holding("ITEM-1")
        self._item(self.item_holding, barcode=None, shelfmark=None)
        self.complete_holding = self._holding("COMPLETE-1")
        self._item(self.complete_holding, barcode="BC-1", shelfmark="A 12")
        self.electronic_holding = self._holding("E-BOOK-1", holding_type="electronic")
        self.db.commit()

        self.original_tenant_session = dependencies.tenant_session

        @contextmanager
        def test_tenant_session(_tenant_id):
            yield self.db

        dependencies.tenant_session = test_tenant_session
        app = FastAPI()
        app.include_router(tenant_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        dependencies.tenant_session = self.original_tenant_session
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def _holding(self, key, holding_type="physical"):
        holding = TenantHolding(
            id=uuid7(),
            tenant_id=self.tenant.id,
            branch_id=uuid.uuid4(),
            manifestation_entity_id=uuid.uuid4(),
            holding_type=holding_type,
            local_holding_key=key,
            status="active",
        )
        self.db.add(holding)
        self.db.flush()
        return holding

    def _item(self, holding, barcode, shelfmark, availability_status="available"):
        item = TenantItem(
            id=uuid7(),
            tenant_id=self.tenant.id,
            holding_id=holding.id,
            barcode=barcode,
            shelfmark=shelfmark,
            availability_status=availability_status,
            lifecycle_status="active",
        )
        self.db.add(item)
        self.db.flush()
        return item

    def _get(self, path="/tenant/data-quality"):
        return self.client.get(
            path,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def test_reports_missing_item_barcode_and_placement(self):
        response = self._get()

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        checks = {check["key"]: check for check in body["checks"]}

        self.assertEqual(body["tenant_id"], str(self.tenant.id))
        self.assertEqual(body["total_findings"], 3)
        self.assertEqual(checks["empty_physical_holding"]["count"], 1)
        self.assertEqual(
            checks["empty_physical_holding"]["records"][0]["holding_key"],
            "EMPTY-1",
        )
        self.assertEqual(checks["missing_barcode"]["count"], 1)
        self.assertEqual(checks["missing_shelfmark"]["count"], 1)
        self.assertNotIn(
            "E-BOOK-1",
            [
                record["holding_key"]
                for check in body["checks"]
                for record in check["records"]
            ],
        )

    def test_limit_caps_returned_examples_but_not_finding_count(self):
        self._holding("EMPTY-2")
        self.db.commit()

        response = self._get("/tenant/data-quality?limit=1")
        checks = {check["key"]: check for check in response.json()["checks"]}

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total_findings"], 4)
        self.assertEqual(checks["empty_physical_holding"]["count"], 2)
        self.assertEqual(len(checks["empty_physical_holding"]["records"]), 1)

    def test_summary_reports_every_item_status_for_the_chart(self):
        for index, status in enumerate(("on_loan", "reference", "lost", "unknown"), start=1):
            holding = self._holding(f"STATUS-{index}")
            self._item(
                holding,
                barcode=f"STATUS-BC-{index}",
                shelfmark=f"S-{index}",
                availability_status=status,
            )
        self.db.commit()

        response = self._get("/tenant/summary")
        summary = response.json()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(summary["available"], 2)
        self.assertEqual(summary["on_loan"], 1)
        self.assertEqual(summary["reference"], 1)
        self.assertEqual(summary["lost"], 1)
        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(summary["other_status"], 0)
    def test_endpoint_requires_a_session(self):
        response = self.client.get("/tenant/data-quality")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()