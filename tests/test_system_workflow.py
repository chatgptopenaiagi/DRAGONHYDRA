"""Selected-match orchestration uses the existing engine and isolated fiction."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra import market_signals, public_results, system_workflow
from dragonhydra.cognition import evaluation, memory, models
from dragonhydra.product import Product
from dragonhydra.jobs import Jobs


class SystemWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='dragonhydra-workflow-')
        self.addCleanup(self.folder.cleanup)
        self.product = Product(Path(self.folder.name))
        self.initial = datetime.now(timezone.utc)
        day = self.initial.date()
        self.document = {'name': 'Fictional workflow test league', 'matches': [
            {'date': str(day - timedelta(days=20-index)), 'team1': 'Home' if index == 0 else f'Other {index}',
             'team2': 'Away' if index == 1 else f'Visitor {index}',
             'score': {'ft': [index % 3, (index+1) % 2]}} for index in range(8)] + [
            {'date': str(day + timedelta(days=5)), 'team1': 'Home', 'team2': 'Away'},
            {'date': str(day + timedelta(days=6)), 'team1': 'Other target', 'team2': 'Other visitor'}]}
        self.ingest('first')
        self.target = next(row for row in self.product.rows() if row['home'] == 'Home' and row['outcome'] is None)
        self.match_id = self.product.match_id(self.target)
        self.other_id = self.product.match_id(next(row for row in self.product.rows() if row['home'] == 'Other target'))

    def ingest(self, acquisition):
        with closing(self.product.connect()) as db:
            return public_results.ingest_bytes(db, json.dumps(self.document).encode(),
                source_id='fictional-workflow-source', source_url='fictional:test-only', acquisition_id=acquisition)

    def test_history_is_read_only_before_explicit_engine_command(self):
        with patch.object(evaluation, 'chronological_holdout', side_effect=AssertionError('implicit model diagnostic')):
            report = system_workflow.match_history(self.product, self.match_id)
        self.assertEqual(report['counts'], {'models': 0, 'predictions': 0, 'outcomes': 0, 'evaluations': 0})
        self.assertEqual(report['present_knowledge_holdout']['mode'], 'PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT')
        self.assertFalse(report['present_knowledge_holdout']['available'])
        self.assertEqual(report['present_knowledge_holdout']['reason'], 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED')
        with closing(self.product.connect()) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='cognitive_records'").fetchone())

    def test_selected_forecast_is_persisted_and_replay_keeps_original_records(self):
        with patch.object(public_results, 'import_file', side_effect=AssertionError('implicit import')):
            result = system_workflow.forecast_match(self.product, self.match_id, 'job-forecast')
        self.assertEqual(result['status'], 'persisted')
        self.assertEqual(len(result['model_runs']), 5)
        self.assertEqual(len(result['predictions']), 5)
        self.assertTrue(all(row['target_evidence_id'] == self.target['evidence_id'] for row in result['predictions']))
        self.assertTrue(all(len(row['input_evidence_ids']) == 8 for row in result['model_runs']))
        with patch.object(models, 'forecast', side_effect=AssertionError('recalculated original command')):
            replay = system_workflow.forecast_match(self.product, self.match_id, 'job-forecast')
        self.assertTrue(replay['duplicate'])
        self.assertEqual(result['predictions'], replay['predictions'])
        self.assertEqual(system_workflow.match_history(self.product, self.match_id)['counts']['predictions'], 5)
        self.assertEqual(system_workflow.match_history(self.product, self.other_id)['counts']['predictions'], 0)
        with self.assertRaisesRegex(ValueError, 'WORKFLOW_RUN_IDENTITY_CONFLICT'):
            system_workflow.forecast_match(self.product, self.other_id, 'job-forecast')

    def test_finished_and_connector_targets_are_not_retrospective_forecasts(self):
        finished = next(row for row in self.product.rows() if row['outcome'] is not None)
        with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_FORECAST_REQUIRES_UNPLAYED_TARGET'):
            system_workflow.forecast_match(self.product, self.product.match_id(finished), 'finished-job')
        with patch.object(self.product, 'find', return_value={'_connector': {'sport': 'football'}}):
            with self.assertRaisesRegex(ValueError, 'SOURCE_FORECAST_WORKFLOW_UNAVAILABLE'):
                system_workflow.forecast_match(self.product, self.match_id, 'connector-job')
        with self.assertRaisesRegex(ValueError, 'CUTOFF_AFTER_ACTUAL_TIME'):
            system_workflow.match_history(self.product, self.match_id, '2099-01-01T00:00:00Z')

    def test_interrupted_partial_run_is_visible_without_recomputation(self):
        with patch.object(memory, 'record_prediction', side_effect=ValueError('interrupted fixture')):
            with self.assertRaisesRegex(ValueError, 'interrupted fixture'):
                system_workflow.forecast_match(self.product, self.match_id, 'partial-job')
        with patch.object(models, 'forecast', side_effect=AssertionError('must not recompute partial run')):
            replay = system_workflow.forecast_match(self.product, self.match_id, 'partial-job')
        self.assertEqual(replay['status'], 'partial')
        self.assertEqual(replay['reason'], 'PARTIAL_RUN_REQUIRES_REVIEW')
        self.assertEqual(len(replay['model_runs']), 1)
        self.assertEqual(replay['predictions'], [])

    def test_existing_jobs_bind_operation_to_the_durable_job_id(self):
        jobs = Jobs(self.product)
        queued = jobs.submit('forecast', {'match_id': self.match_id}, 'joomla:7', 'forecast-click')
        duplicate = jobs.submit('forecast', {'match_id': self.match_id}, 'joomla:7', 'forecast-click')
        self.assertEqual(queued['id'], duplicate['id'])
        self.assertTrue(jobs.run_once())
        completed = jobs.get(queued['id'])
        self.assertEqual(completed['status'], 'succeeded', completed['error'])
        self.assertEqual(completed['result']['run_id'], queued['id'])
        self.assertEqual(len(completed['result']['predictions']), 5)
        evaluation_job = jobs.submit('evaluation', {'match_id': self.match_id}, 'joomla:7', 'evaluate-click')
        self.assertTrue(jobs.run_once())
        pending = jobs.get(evaluation_job['id'])
        self.assertEqual(pending['status'], 'succeeded')
        self.assertEqual(pending['result']['status'], 'pending')
        self.assertEqual(pending['result']['reason'], 'LATER_RETAINED_OUTCOME_UNAVAILABLE')

    def test_history_never_repairs_a_damaged_memory_schema(self):
        system_workflow.forecast_match(self.product, self.match_id, 'valid-before-damage')
        with closing(self.product.connect()) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.commit()
        with self.assertRaisesRegex(ValueError, 'COGNITIVE_STORE_INCOMPLETE'):
            system_workflow.match_history(self.product, self.match_id)
        with closing(self.product.connect()) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='cognitive_records_no_update'").fetchone())
            db.execute('DROP TABLE cognitive_receipts')
            db.commit()
        with self.assertRaisesRegex(ValueError, 'COGNITIVE_STORE_INCOMPLETE'):
            system_workflow.match_history(self.product, self.match_id)
        with closing(self.product.connect()) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='cognitive_receipts'").fetchone())

    def test_memory_readonly_path_does_not_initialize_or_repair(self):
        with self.assertRaises(sqlite3.OperationalError):
            memory.as_of(self.product.db_path, datetime.now(timezone.utc).isoformat(), readonly=True)
        system_workflow.forecast_match(self.product, self.match_id, 'readonly-read')
        with patch.object(memory, '_schema', side_effect=AssertionError('read path attempted schema mutation')):
            records = memory.as_of(self.product.db_path, datetime.now(timezone.utc).isoformat(), readonly=True)
        self.assertEqual(len(records['predictions']), 5)

    def test_outcome_is_pending_then_real_later_fixture_revision_is_scored(self):
        forecast = system_workflow.forecast_match(self.product, self.match_id, 'forecast-before-result')
        pending = system_workflow.evaluate_match(self.product, self.match_id, 'pending-evaluation')
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['reason'], 'LATER_RETAINED_OUTCOME_UNAVAILABLE')
        self.assertEqual(pending['persisted_evaluations'], [])
        later = self.initial + timedelta(days=9)
        stamp = later.isoformat().replace('+00:00', 'Z')
        class LaterDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return later.astimezone(tz) if tz else later.replace(tzinfo=None)
        self.document['matches'][-2]['score'] = {'ft': [2, 1]}
        with patch.object(public_results, '_now', return_value=stamp), patch.object(memory, '_now', return_value=stamp), \
                patch.object(system_workflow, '_now', return_value=stamp), patch.object(evaluation, 'datetime', LaterDatetime):
            self.ingest('later-real-source-revision-in-fictional-test')
            result = system_workflow.evaluate_match(self.product, self.match_id, 'result-evaluation')
            self.assertEqual(result['status'], 'persisted')
            self.assertEqual(len(result['persisted_evaluations']), 2 * len(models.NAMES))
            self.assertEqual(result['history']['counts']['outcomes'], 1)
            self.assertEqual(result['history']['counts']['evaluations'], 2 * len(models.NAMES))
            for group in result['history']['operational']['groups']:
                self.assertEqual(group['metrics']['brier']['sample_size'], 1)
                self.assertEqual(group['cases'][0]['actual_outcome'], 'home')
                self.assertEqual(group['cases'][0]['fixture_key'], self.target['fixture_key'])
            # A duplicate forecast command still returns the original pre-result
            # records after the source target has acquired a later result.
            replay = system_workflow.forecast_match(self.product, self.match_id, 'forecast-before-result')
            self.assertTrue(replay['duplicate'])
            self.assertEqual(replay['predictions'], forecast['predictions'])
            duplicate = system_workflow.evaluate_match(self.product, self.match_id, 'result-evaluation')
            self.assertTrue(duplicate['duplicate'])
            self.assertTrue(all(row['duplicate'] for row in duplicate['persisted_evaluations']))
            self.assertEqual(duplicate['history']['counts']['evaluations'], 2 * len(models.NAMES))
        original = system_workflow.match_history(self.product, self.match_id)
        self.assertEqual(original['counts']['outcomes'], 0)
        self.assertEqual(original['counts']['evaluations'], 0)


class WorkflowOddsKnownAnswerTests(unittest.TestCase):
    def test_complete_market_reciprocals_margin_and_explicit_proportional_estimates(self):
        stamp = '2026-01-01T12:00:00Z'
        quotes = []
        for outcome, price in [('home', '2'), ('draw', '3'), ('away', '4')]:
            quotes.append({'data_origin': 'synthetic', 'evidence_id': outcome, 'source_id': 'unit',
                'provider_id': 'unit', 'feed_id': 'unit', 'snapshot_id': 'one-complete-snapshot',
                'outcome': outcome, 'odds_original': price, 'odds_format': 'decimal',
                'received_at': stamp, 'persisted_at': stamp, 'usable_at': stamp,
                'event_id': 'fixture', 'competition': 'league', 'home': 'Home', 'away': 'Away',
                'market_type': '1x2', 'period': 'full_time', 'status': 'pregame',
                'settlement': 'regulation', 'line': None})
        margin = market_signals.compute_signals(quotes, stamp)['overrounds'][0]
        with localcontext() as context:
            context.prec = 34
            self.assertEqual(Decimal(margin['overround']['value']), Decimal(1)/12)
            for outcome, numerator in [('home', 6), ('draw', 4), ('away', 3)]:
                estimate = margin['proportional_margin_removed_estimates'][outcome]
                self.assertEqual(Decimal(estimate['value']), Decimal(numerator)/13)
                self.assertIn('not true probability', estimate['interpretation'])
        for invalid in [0, 1, -2, 'NaN', 'Infinity', True]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                market_signals.implied_probability(invalid)


if __name__ == '__main__':
    unittest.main()
