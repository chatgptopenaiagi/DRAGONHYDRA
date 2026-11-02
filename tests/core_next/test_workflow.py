"""Selected-match workflow uses actual existing math on isolated fictional data."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra import public_results
from dragonhydra.cognition import evaluation, memory, models
from dragonhydra.kernel import workflow
from dragonhydra.kernel.ports import MemoryPort
from dragonhydra.product import Product


LAB = Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=LAB/'tests', prefix='workflow-')
        self.addCleanup(temporary.cleanup)
        self.product = Product(Path(temporary.name))
        self.initial = datetime.now(timezone.utc)
        self.clock = [None]
        day = self.initial.date()
        self.document = {'name': 'Fictional CORE NEXT workflow league', 'matches': [
            {'date': str(day-timedelta(days=20-index)), 'team1': 'Home' if index == 0 else f'Other {index}',
             'team2': 'Away' if index == 1 else f'Visitor {index}', 'score': {'ft': [index % 3, (index+1) % 2]}}
            for index in range(8)] + [
            {'date': str(day+timedelta(days=5)), 'team1': 'Home', 'team2': 'Away'},
            {'date': str(day+timedelta(days=6)), 'team1': 'Other target', 'team2': 'Other visitor'}]}
        self.ingest('initial')
        self.data = self.product.kernel.engines['data']
        self.target = next(row for row in self.data.rows() if row['home'] == 'Home' and row['outcome'] is None)
        self.match_id = self.data.match_id(self.target)
        self.other_id = self.data.match_id(next(row for row in self.data.rows() if row['home'] == 'Other target'))
        self.memory_port = MemoryPort(lambda cutoff: memory.as_of(self.product.db_path, cutoff, readonly=True),
            lambda draft: memory.record_model_run(self.product.db_path, draft),
            lambda draft: memory.record_prediction(self.product.db_path, draft),
            lambda eid: memory.record_outcome(self.product.db_path, eid))

    def now(self):
        return self.clock[0] or datetime.now(timezone.utc).isoformat()

    def ingest(self, acquisition):
        with closing(self.product.connect()) as db:
            public_results.ingest_bytes(db, json.dumps(self.document).encode(),
                source_id='fictional-core-next-workflow', source_url='fictional:test-only', acquisition_id=acquisition)

    def forecast(self, run_id, match_id=None):
        return workflow.forecast_match(data=self.data, model_backend=models, memory=self.memory_port,
            db_path=self.product.db_path, clock=self.now, match_id=match_id or self.match_id, run_id=run_id)

    def history(self, match_id=None, cutoff=None):
        return workflow.match_history(data=self.data, view=self.memory_port.view,
            db_path=self.product.db_path, clock=self.now, match_id=match_id or self.match_id, cutoff=cutoff)

    def evaluate(self, run_id):
        return workflow.evaluate_match(data=self.data, memory=self.memory_port,
            persist=lambda draft: memory.record_evaluation(self.product.db_path, draft),
            db_path=self.product.db_path, clock=self.now, match_id=self.match_id, run_id=run_id)

    def test_history_does_not_create_schema_run_model_or_diagnostic(self):
        with closing(self.product.connect()) as db:
            before = list(db.iterdump())
        with patch.object(models, 'forecast', side_effect=AssertionError('implicit forecast')), \
             patch.object(evaluation, 'chronological_holdout', side_effect=AssertionError('implicit diagnostic')), \
             patch.object(public_results, 'import_file', side_effect=AssertionError('implicit import')):
            report = self.history()
        self.assertEqual(report['counts'], {'models': 0, 'predictions': 0, 'outcomes': 0, 'evaluations': 0})
        self.assertEqual(report['present_knowledge_holdout']['reason'], 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED')
        with closing(self.product.connect()) as db:
            self.assertEqual(before, list(db.iterdump()))

    def test_forecast_provenance_is_persisted_and_same_run_replays_original_records(self):
        result = self.forecast('synthetic-durable-run')
        self.assertEqual(result['status'], 'persisted')
        self.assertEqual(len(result['model_runs']), 5)
        self.assertEqual(len(result['predictions']), 5)
        for model in result['model_runs']:
            proof = model['parameters']['workflow']
            self.assertEqual(proof['match_id'], self.match_id)
            self.assertEqual(proof['input_versions'], model['input_evidence_ids'])
            self.assertEqual(len(model['input_evidence_ids']), 8)
            self.assertIn('generated_at', proof)
            self.assertIn('version', proof['build'])
            self.assertEqual(model['model_version'], models.VERSION)
        with patch.object(models, 'forecast', side_effect=AssertionError('same run must not recalculate')):
            replay = self.forecast('synthetic-durable-run')
        self.assertTrue(replay['duplicate'])
        self.assertEqual(result['model_runs'], replay['model_runs'])
        self.assertEqual(result['predictions'], replay['predictions'])
        self.assertEqual(self.history()['counts']['predictions'], 5)
        self.assertEqual(self.history(self.other_id)['counts']['predictions'], 0)
        with self.assertRaisesRegex(ValueError, 'WORKFLOW_RUN_IDENTITY_CONFLICT'):
            self.forecast('synthetic-durable-run', self.other_id)

    def test_partial_run_is_visible_without_recalculation(self):
        with patch.object(memory, 'record_prediction', side_effect=ValueError('SYNTHETIC_INTERRUPTION')):
            with self.assertRaisesRegex(ValueError, 'SYNTHETIC_INTERRUPTION'):
                self.forecast('partial-run')
        with patch.object(models, 'forecast', side_effect=AssertionError('partial run must not recalculate')):
            replay = self.forecast('partial-run')
        self.assertEqual(replay['status'], 'partial')
        self.assertEqual(replay['reason'], 'PARTIAL_RUN_REQUIRES_REVIEW')
        self.assertEqual(len(replay['model_runs']), 1)
        self.assertEqual(replay['predictions'], [])

    def test_finished_unsupported_and_future_cutoff_abstain(self):
        finished = next(row for row in self.data.rows() if row['outcome'] is not None)
        with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_FORECAST_REQUIRES_UNPLAYED_TARGET'):
            self.forecast('finished-run', self.data.match_id(finished))
        with patch.object(self.data, 'find', return_value={'_connector': {'sport': 'football'}}):
            with self.assertRaisesRegex(ValueError, 'SOURCE_FORECAST_WORKFLOW_UNAVAILABLE'):
                self.forecast('unsupported-run', 'f'*64)
        with self.assertRaisesRegex(ValueError, 'CUTOFF_AFTER_ACTUAL_TIME'):
            self.history(cutoff='2099-01-01T00:00:00Z')

    def test_real_later_revision_in_fictional_clock_fixture_is_pending_then_scored(self):
        forecast = self.forecast('forecast-before-result')
        pending = self.evaluate('pending-run')
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['reason'], 'LATER_RETAINED_OUTCOME_UNAVAILABLE')
        self.assertEqual(pending['persisted_evaluations'], [])
        later = self.initial+timedelta(days=9)
        stamp = later.isoformat().replace('+00:00', 'Z')
        class LaterDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return later.astimezone(tz) if tz else later.replace(tzinfo=None)
        self.document['matches'][-2]['score'] = {'ft': [2, 1]}
        self.clock[0] = stamp
        with patch.object(public_results, '_now', return_value=stamp), patch.object(memory, '_now', return_value=stamp), \
             patch.object(evaluation, 'datetime', LaterDatetime):
            self.ingest('later-source-revision-in-fictional-test')
            result = self.evaluate('eligible-evaluation-run')
            self.assertEqual(result['status'], 'persisted')
            self.assertEqual(len(result['persisted_evaluations']), 2*len(models.NAMES))
            self.assertEqual(result['history']['counts']['outcomes'], 1)
            self.assertEqual(result['history']['counts']['evaluations'], 2*len(models.NAMES))
            for group in result['history']['operational']['groups']:
                self.assertEqual(group['metrics']['brier']['sample_size'], 1)
            replay = self.forecast('forecast-before-result')
            self.assertEqual(replay['predictions'], forecast['predictions'])
            duplicate = self.evaluate('eligible-evaluation-run')
            self.assertTrue(duplicate['duplicate'])
            self.assertTrue(all(item['duplicate'] for item in duplicate['persisted_evaluations']))
        self.clock[0] = None
        self.assertEqual(self.history()['counts']['outcomes'], 0)


if __name__ == '__main__':
    unittest.main()
