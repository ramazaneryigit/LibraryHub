"""Isolated SQLite contract tests; no application database is used."""
import os
import unittest
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite://')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models import Entity, EntityMerge, SourceRecord, Work, ReconciliationCandidate, ReconciliationDecision
from app.routers.reconciliation import router
from app.services.reconciliation import generate_work_candidates


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.source = SourceRecord(source_system='test', source_record_id='controlled', record_type='work',
                                   raw_data={'title': 'Bilgi Yönetimi Giriş', 'language': 'tr', 'work_type': 'textbook'})
        self.db.add(self.source)
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

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


if __name__ == '__main__':
    unittest.main()
