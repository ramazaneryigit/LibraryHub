"""Isolated SQLite contract tests; no application database is used."""
import os
import re
import unittest
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault('DATABASE_URL', 'sqlite://')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ids import uuid7
from app.core.security import (
    hash_password,
    hash_session_token,
    new_session_token,
)
from app.db import Base, get_db
from app.db.models import (
    Entity,
    EntityMerge,
    ReconciliationCandidate,
    ReconciliationDecision,
    SourceRecord,
    Tenant,
    User,
    UserSession,
    Work,
)
from app.api.v1.routes.reconciliation import router
from app.services.reconciliation import compare_field, generate_work_candidates


def _trigrams(value):
    """Trigram set built the way pg_trgm builds it: per word, padded '  word '."""
    result = set()
    for word in re.split(r'[^\w]+', value or ''):
        if not word:
            continue
        padded = '  ' + word + ' '
        result.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return result


def _sqlite_trigram_similarity(left, right):
    """Stand-in for pg_trgm's similarity() on the SQLite test engine.

    |shared trigrams| / |union|, which mirrors pg_trgm closely enough for policy
    tests. It is NOT bit-identical to pg_trgm, and the production query also uses
    the `%` operator for index-backed blocking -- SQLite has no equivalent, so
    that filter is skipped there. These tests therefore exercise policy
    behaviour, not the exact scoring of a deployed PostgreSQL instance.
    """
    a = _trigrams(left)
    b = _trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        # SQLite has no schemas, but the Control Plane and Tenant Data Plane
        # tables live in `control` and `tenant`. Attach in-memory databases
        # under those names before create_all; StaticPool keeps everything on
        # the one shared connection, so the attachments stay visible.
        # See docs/architecture-v2.md §0.5 and §0.7.
        with self.engine.begin() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS control")
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS tenant")
            # pg_trgm is a PostgreSQL extension and the code under test calls
            # its similarity() function, so provide it on this engine.
            connection.connection.create_function(
                'similarity', 2, _sqlite_trigram_similarity
            )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.source = SourceRecord(source_system='test', source_record_id='controlled', record_type='work',
                                   raw_data={'title': 'Bilgi Yönetimi Giriş', 'language': 'tr', 'work_type': 'textbook'})
        self.db.add(self.source)
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db

        # The reconciliation routes write the global plane, which now requires an
        # administrator. These tests go through a real session rather than
        # overriding the dependency, so the authorization path is exercised
        # rather than bypassed.
        tenant = Tenant(slug='test', display_name='Test Kütüphanesi')
        self.db.add(tenant)
        self.db.flush()

        admin = User(
            tenant_id=tenant.id,
            email='admin@test.edu.tr',
            display_name='Test Yönetici',
            password_hash=hash_password('parola-12345'),
            role='admin',
            email_verified_at=datetime.now(timezone.utc),
        )
        self.db.add(admin)
        self.db.flush()

        token = new_session_token()

        self.db.add(
            UserSession(
                id=uuid7(),
                user_id=admin.id,
                token_hash=hash_session_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        self.db.commit()

        self.client = TestClient(app)
        self.client.headers.update({'Authorization': f'Bearer {token}'})

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def candidate(self, score, title='Bilgi Yönetimine Giriş'):
        entity = Entity(entity_type='WORK')
        self.db.add(entity)
        self.db.flush()
        self.db.add(Work(entity_id=entity.id, canonical_title=title, original_language='tr', work_type='textbook'))
        candidate = ReconciliationCandidate(source_record_id=self.source.id, candidate_entity_id=entity.id,
                                            score=score, method='work_fuzzy_title_v2', evidence={'title_similarity': score})
        self.db.add(candidate)
        self.db.commit()
        return candidate

    def evaluate(self):
        response = self.client.get(f'/reconciliation/source-records/{self.source.id}/evaluation')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result['automatic_acceptance_eligible'])
        return result

    def test_no_candidates_is_unresolved_not_new_entity(self):
        result = self.evaluate()
        self.assertEqual(result['recommendation'], 'unresolved')
        self.assertIsNone(result['score_margin'])

    def test_single_perfect_candidate_still_requires_review(self):
        self.candidate(1.0)
        result = self.evaluate()
        self.assertIsNone(result['second_candidate'])
        self.assertIsNone(result['score_margin'])
        self.assertEqual(result['recommendation'], 'manual_review')

    def test_close_scores_and_tie(self):
        a = self.candidate(.97)
        b = self.candidate(.96)
        self.assertEqual(self.evaluate()['score_margin'], .01)
        b.score = a.score
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result['score_margin'], 0)
        self.assertIn('top_score_tie', result['reason_codes'])
        self.assertEqual(result['ranking'], self.evaluate()['ranking'])

    def test_canonical_chain_grouped_before_margin(self):
        a, b, c, d = [self.candidate(score) for score in (.97, .96, .95, .70)]
        self.db.add_all([
            EntityMerge(source_entity_id=a.candidate_entity_id, target_entity_id=b.candidate_entity_id),
            EntityMerge(source_entity_id=b.candidate_entity_id, target_entity_id=c.candidate_entity_id),
        ])
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result['distinct_candidate_count'], 2)
        self.assertEqual(result['score_margin'], .27)
        self.assertEqual(len(result['top_candidate']['members']), 3)
        self.assertEqual(result['top_candidate']['representative_candidate_id'], str(a.id))
        self.assertEqual(result['top_candidate']['canonical_entity_id'], str(c.candidate_entity_id))

    def test_cycle_is_excluded(self):
        a, b = self.candidate(.99), self.candidate(.98)
        self.db.add_all([
            EntityMerge(source_entity_id=a.candidate_entity_id, target_entity_id=b.candidate_entity_id),
            EntityMerge(source_entity_id=b.candidate_entity_id, target_entity_id=a.candidate_entity_id),
        ])
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result['distinct_candidate_count'], 0)
        self.assertEqual(len(result['excluded_candidates']), 2)

    def test_missing_work_is_excluded(self):
        candidate = self.candidate(.9)
        self.db.delete(self.db.get(Work, candidate.candidate_entity_id))
        self.db.commit()
        self.assertEqual(self.evaluate()['excluded_candidates'][0]['reason'], 'canonical_work_missing')

    def test_existing_decision_and_evidence_unchanged_no_writes(self):
        candidate = self.candidate(.9)
        decision = ReconciliationDecision(source_record_id=self.source.id, candidate_id=candidate.id,
                                           status='accepted', origin='manual', reason='reviewed')
        self.db.add(decision)
        self.db.commit()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().split()[0].upper())
        event.listen(self.engine, 'before_cursor_execute', capture)
        result = self.evaluate()
        event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertFalse({'INSERT', 'UPDATE', 'DELETE'}.intersection(statements))
        self.assertEqual(result['current_decision']['status'], 'accepted')
        self.db.refresh(candidate)
        self.assertEqual(candidate.evidence, {'title_similarity': .9})
        self.assertFalse(self.db.dirty)

    def test_missing_source_fields_and_error_responses(self):
        self.source.raw_data = []
        self.db.commit()
        self.assertEqual(self.evaluate()['missing_source_fields'], ['title', 'language', 'work_type'])
        self.source.record_type = 'person'
        self.db.commit()
        self.assertEqual(self.client.get(f'/reconciliation/source-records/{self.source.id}/evaluation').status_code, 400)
        self.assertEqual(self.client.get(f'/reconciliation/source-records/{uuid.uuid4()}/evaluation').status_code, 404)
        self.assertEqual(self.client.get('/reconciliation/source-records/not-a-uuid/evaluation').status_code, 422)

    def test_existing_generator_to_evaluation(self):
        self.candidate(.1)
        candidates = generate_work_candidates(self.db, self.source)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0].score, .9667, places=4)
        result = self.evaluate()
        self.assertEqual(result['top_candidate']['score'], .9667)
        self.assertEqual(result['top_candidate']['members'][0]['evidence']['language_match'], True)

    def test_field_comparison_states(self):
        for left, right, expected in [
            (" TR ", "tr", "match"), ("tr", "en", "conflict"),
            (None, "tr", "missing_source"), ("tr", "  ", "missing_candidate"),
            ("", None, "missing_both"), ([], "tr", "invalid_value"),
            ("tr", 5, "invalid_value"), ("!!!", "tr", "missing_source"),
        ]:
            with self.subTest(left=left, right=right):
                result = compare_field(left, right)
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["source_value"], left)
                self.assertEqual(result["candidate_value"], right)

    def test_conflict_missing_and_invalid_have_distinct_evidence(self):
        candidate = self.candidate(.1)
        for value, status in [("en", "conflict"), (None, "missing_source"), ([], "invalid_value")]:
            with self.subTest(status=status):
                self.source.raw_data = {"title": "Bilgi Yönetimi Giriş", "language": value, "work_type": "textbook"}
                self.db.commit()
                generated = generate_work_candidates(self.db, self.source)[0]
                self.assertAlmostEqual(generated.score, .8167, places=4)
                self.assertEqual(generated.evidence["field_comparisons"]["language"]["status"], status)
                self.assertFalse(generated.evidence["language_match"])
                self.assertIn(f"top_candidate_language_{status}", self.evaluate()["reason_codes"])

    def test_work_type_candidate_missing_and_both_missing(self):
        candidate = self.candidate(.1)
        work = self.db.get(Work, candidate.candidate_entity_id)
        work.work_type = None
        self.db.commit()
        generated = generate_work_candidates(self.db, self.source)[0]
        self.assertEqual(generated.evidence["field_comparisons"]["work_type"]["status"], "missing_candidate")
        self.source.raw_data = {"title": "Bilgi Yönetimi Giriş", "language": "tr"}
        self.db.commit()
        generated = generate_work_candidates(self.db, self.source)[0]
        self.assertEqual(generated.evidence["field_comparisons"]["work_type"]["status"], "missing_both")

    def test_legacy_false_is_not_inferred_as_conflict(self):
        candidate = self.candidate(.8)
        candidate.evidence = {"language_match": False, "work_type_match": False}
        self.db.commit()
        result = self.evaluate()
        self.assertIn("field_comparison_unavailable", result["reason_codes"])
        self.assertFalse(any("conflict" in code for code in result["reason_codes"]))


    def fresh_candidate(self):
        self.candidate(.1)
        return generate_work_candidates(self.db, self.source)[0]

    def test_generated_inputs_are_fresh(self):
        self.fresh_candidate()
        result = self.evaluate()
        self.assertEqual(result["top_candidate"]["freshness"]["status"], "fresh")
        self.assertTrue(result["stored_candidate_inputs_current"])
        self.assertFalse(result["requires_candidate_regeneration"])
        self.assertNotIn("candidate_freshness_not_verified", result["reason_codes"])

    def test_changed_source_is_stale_and_regeneration_restores_freshness(self):
        candidate = self.fresh_candidate()
        original_evidence = candidate.evidence.copy()
        self.source.raw_data = {**self.source.raw_data, "language": "en"}
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result["top_candidate"]["freshness"]["status"], "stale")
        self.assertIn("source_data_changed", result["top_candidate"]["freshness"]["reason_codes"])
        self.assertTrue(result["requires_candidate_regeneration"])
        self.assertEqual(candidate.evidence, original_evidence)
        regenerated = generate_work_candidates(self.db, self.source)[0]
        self.assertEqual(regenerated.id, candidate.id)
        self.assertEqual(self.evaluate()["top_candidate"]["freshness"]["status"], "fresh")

    def test_each_scoring_work_field_invalidates_evidence(self):
        candidate = self.fresh_candidate()
        work = self.db.get(Work, candidate.candidate_entity_id)
        for field, value in [("canonical_title", "Bilgi Yönetimi Giriş"),
                             ("original_language", "en"), ("work_type", "novel")]:
            with self.subTest(field=field):
                setattr(work, field, value)
                self.db.commit()
                freshness = self.evaluate()["top_candidate"]["freshness"]
                self.assertEqual(freshness["status"], "stale")
                self.assertIn("work_data_changed", freshness["reason_codes"])
                generate_work_candidates(self.db, self.source)
                self.assertEqual(self.evaluate()["top_candidate"]["freshness"]["status"], "fresh")

    def test_source_key_order_does_not_invalidate_evidence(self):
        self.fresh_candidate()
        self.source.raw_data = dict(reversed(list(self.source.raw_data.items())))
        self.db.commit()
        self.assertEqual(self.evaluate()["top_candidate"]["freshness"]["status"], "fresh")

    def test_redirect_invalidates_prior_canonical_identity(self):
        a = self.fresh_candidate()
        b = self.candidate(.1)
        self.db.add(EntityMerge(source_entity_id=a.candidate_entity_id, target_entity_id=b.candidate_entity_id))
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result["distinct_candidate_count"], 1)
        self.assertIn("canonical_identity_changed", result["top_candidate"]["freshness"]["reason_codes"])

    def test_old_and_malformed_fingerprints_are_unknown(self):
        candidate = self.candidate(.9)
        self.assertEqual(self.evaluate()["top_candidate"]["freshness"]["status"], "unknown")
        for snapshot in [{"version": "future"}, {"version": "work_inputs_v1", "source_hash": []}]:
            candidate.evidence = {"input_fingerprints": snapshot}
            self.db.commit()
            self.assertEqual(self.evaluate()["top_candidate"]["freshness"]["status"], "unknown")

    def test_method_change_is_stale(self):
        candidate = self.fresh_candidate()
        candidate.method = "work_fuzzy_title_v3"
        self.db.commit()
        self.assertIn("matching_method_changed", self.evaluate()["top_candidate"]["freshness"]["reason_codes"])

    def test_unmatched_old_candidate_remains_stale_after_generation(self):
        candidate = self.fresh_candidate()
        self.source.raw_data = {"title": "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"}
        self.db.commit()
        self.assertEqual(generate_work_candidates(self.db, self.source), [])
        result = self.evaluate()
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["top_candidate"]["freshness"]["status"], "stale")
        self.assertFalse(result["stored_candidate_inputs_current"])


    def decide(self, candidate, status="accepted", origin="manual"):
        return self.client.post(f'/reconciliation/source-records/{self.source.id}/decision',
                                json={"candidate_id": str(candidate.id) if candidate else None,
                                      "status": status, "origin": origin})

    def assert_no_decision(self):
        self.assertIsNone(self.db.scalar(select(ReconciliationDecision).where(
            ReconciliationDecision.source_record_id == self.source.id)))

    def test_fresh_manual_acceptance_and_duplicate_preservation(self):
        candidate = self.fresh_candidate()
        response = self.decide(candidate)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertIsNotNone(response.json()["reviewed_at"])
        self.assertEqual(self.decide(candidate).status_code, 409)
        self.assertEqual(self.evaluate()["current_decision"]["id"], response.json()["id"])

    def test_stale_acceptance_blocked_then_regeneration_allows_review(self):
        candidate = self.fresh_candidate()
        self.source.raw_data = {**self.source.raw_data, "language": "en"}
        self.db.commit()
        response = self.decide(candidate)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["freshness"]["status"], "stale")
        self.assert_no_decision()
        generate_work_candidates(self.db, self.source)
        # A conflict is review evidence, not a categorical ban on human judgment.
        self.assertEqual(self.decide(candidate).status_code, 201)

    def test_unknown_evidence_cannot_be_accepted(self):
        response = self.decide(self.candidate(.99))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["freshness"]["status"], "unknown")
        self.assert_no_decision()

    def test_automatic_acceptance_blocked_even_when_fresh(self):
        response = self.decide(self.fresh_candidate(), origin="automatic")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "automatic_acceptance_not_calibrated")
        self.assert_no_decision()

    def test_rejection_with_legacy_evidence_still_allowed(self):
        self.assertEqual(self.decide(self.candidate(.7), status="rejected").status_code, 201)

    def test_acceptance_canonical_cycle_and_missing_work(self):
        a = self.fresh_candidate()
        b = self.candidate(.7)
        self.db.add_all([
            EntityMerge(source_entity_id=a.candidate_entity_id, target_entity_id=b.candidate_entity_id),
            EntityMerge(source_entity_id=b.candidate_entity_id, target_entity_id=a.candidate_entity_id),
        ])
        self.db.commit()
        response = self.decide(a)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "canonical_cycle")
        self.assert_no_decision()
        c = self.candidate(.5)
        self.db.delete(self.db.get(Work, c.candidate_entity_id))
        self.db.commit()
        self.assertEqual(self.decide(c).json()["detail"]["code"], "canonical_work_missing")
        self.assert_no_decision()

    def test_acceptance_rejects_wrong_record_type_and_foreign_candidate(self):
        candidate = self.fresh_candidate()
        self.source.record_type = "person"
        self.db.commit()
        self.assertEqual(self.decide(candidate).status_code, 400)
        self.assert_no_decision()
        other = SourceRecord(source_system="test", source_record_id="other", record_type="work", raw_data={})
        self.db.add(other)
        self.db.commit()
        response = self.client.post(f'/reconciliation/source-records/{other.id}/decision',
                                    json={"candidate_id": str(candidate.id), "status": "accepted"})
        self.assertEqual(response.status_code, 400)


    def test_decision_snapshot_survives_regeneration_and_source_change(self):
        candidate = self.fresh_candidate()
        response = self.decide(candidate)
        self.assertEqual(response.status_code, 201)
        snapshot = response.json()["evidence_snapshot"]
        self.assertEqual(snapshot["candidate"]["score"], .9667)
        self.assertEqual(snapshot["candidate"]["freshness_at_decision"]["status"], "fresh")
        self.source.raw_data = {**self.source.raw_data, "language": "en"}
        self.db.commit()
        generate_work_candidates(self.db, self.source)
        self.assertNotEqual(candidate.score, snapshot["candidate"]["score"])
        decision = self.db.scalar(select(ReconciliationDecision).where(ReconciliationDecision.source_record_id == self.source.id))
        self.db.expire(decision)
        self.assertEqual(decision.evidence_snapshot, snapshot)
        result = self.client.get(f'/reconciliation/source-records/{self.source.id}').json()
        self.assertEqual(result["decision"]["evidence_snapshot"], snapshot)
        self.assertEqual(self.evaluate()["current_decision"]["evidence_snapshot"], snapshot)

    def test_snapshot_preserves_original_canonical_identity_after_merge(self):
        a = self.fresh_candidate()
        snapshot = self.decide(a).json()["evidence_snapshot"]
        b = self.candidate(.5)
        self.db.add(EntityMerge(source_entity_id=a.candidate_entity_id, target_entity_id=b.candidate_entity_id))
        self.db.commit()
        result = self.evaluate()
        self.assertEqual(result["top_candidate"]["canonical_entity_id"], str(b.candidate_entity_id))
        self.assertEqual(result["current_decision"]["evidence_snapshot"], snapshot)
        self.assertEqual(snapshot["candidate"]["canonical_entity_id"], str(a.candidate_entity_id))

    def test_no_candidate_decision_still_captures_source(self):
        response = self.decide(None, status="unresolved")
        self.assertEqual(response.status_code, 201)
        snapshot = response.json()["evidence_snapshot"]
        self.assertIsNone(snapshot["candidate"])
        self.assertEqual(snapshot["source"]["raw_data"], self.source.raw_data)

    def test_legacy_decision_snapshot_remains_null(self):
        decision = ReconciliationDecision(source_record_id=self.source.id, status="unresolved", origin="manual")
        self.db.add(decision)
        self.db.commit()
        self.assertIsNone(self.evaluate()["current_decision"]["evidence_snapshot"])

    def test_snapshot_is_deep_copy_of_nested_evidence(self):
        from app.services.reconciliation_snapshot import capture_decision_snapshot
        candidate = self.fresh_candidate()
        decision = ReconciliationDecision(status="accepted", origin="manual")
        snapshot = capture_decision_snapshot(self.db, self.source, candidate, decision)
        candidate.evidence["field_comparisons"]["language"]["source_value"] = "changed"
        self.source.raw_data["title"] = "changed"
        self.assertEqual(snapshot["candidate"]["evidence"]["field_comparisons"]["language"]["source_value"], "tr")
        self.assertEqual(snapshot["source"]["raw_data"]["title"], "Bilgi Yönetimi Giriş")



if __name__ == '__main__':
    unittest.main()
