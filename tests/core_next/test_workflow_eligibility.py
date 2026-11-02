"""Independent eligibility/provenance checks using only fictional LAB fixtures."""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from dragonhydra.cognition import evaluation, memory, models
from dragonhydra import public_results
from tests.core_next import test_workflow as _fixture


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class WorkflowEligibilityTests(unittest.TestCase):
    setUp = _fixture.WorkflowTests.setUp
    now = _fixture.WorkflowTests.now
    ingest = _fixture.WorkflowTests.ingest
    forecast = _fixture.WorkflowTests.forecast
    history = _fixture.WorkflowTests.history
    evaluate = _fixture.WorkflowTests.evaluate

    def test_known_result_cannot_be_erased_by_a_later_scheduled_revision(self):
        self.document['matches'][-2]['score'] = {'ft': [2, 1]}
        self.ingest('fictional-premature-result')
        del self.document['matches'][-2]['score']
        self.ingest('fictional-reverted-to-scheduled')
        self.assertIsNone(self.data.find(self.match_id)['outcome'])
        with self.assertRaisesRegex(ValueError, 'MODEL_TARGET_OUTCOME_ALREADY_KNOWN'):
            self.forecast('must-not-hide-known-outcome')
        self.assertEqual(self.history()['counts']['predictions'], 0)

    def test_unknown_timezone_near_event_date_does_not_establish_pregame_timing(self):
        self.document['matches'].append({'date': str(self.initial.date()+timedelta(days=1)),
                                        'team1': 'Boundary Home', 'team2': 'Boundary Away'})
        self.ingest('fictional-near-date-boundary')
        target = next(row for row in self.data.rows() if row['home'] == 'Boundary Home')
        with self.assertRaisesRegex(ValueError, 'FUTURE_FIXTURE_TIME_UNCERTAIN'):
            self.forecast('near-event-not-provably-pregame', self.data.match_id(target))
        self.assertEqual(self.history()['counts']['predictions'], 0)

    def test_model_inputs_generation_and_prediction_receipts_keep_distinct_clocks(self):
        result = self.forecast('actual-clock-proof')
        for model in result['model_runs']:
            proof = model['parameters']['workflow']
            self.assertLessEqual(instant(model['data_cutoff']), instant(proof['generated_at']))
            self.assertLessEqual(instant(proof['generated_at']), instant(model['received_at']))
            self.assertLessEqual(instant(model['received_at']), instant(model['persisted_at']))
            self.assertLessEqual(instant(model['persisted_at']), instant(model['usable_at']))
            for source in model['training_manifest']:
                self.assertLessEqual(instant(source['received_at']), instant(source['persisted_at']))
                self.assertLessEqual(instant(source['persisted_at']), instant(source['usable_at']))
                self.assertLessEqual(instant(source['usable_at']), instant(model['data_cutoff']))
        for prediction in result['predictions']:
            self.assertEqual(prediction['decision_cutoff'], prediction['usable_at'])
            self.assertEqual(prediction['predicted_at'], prediction['usable_at'])
            self.assertEqual(prediction['availability_mode'], 'OPERATIONAL_AS_OF_RECEIPT')

    def test_incomplete_run_with_one_prediction_is_not_a_ready_explicit_operation(self):
        original = memory.record_prediction
        calls = []
        def interrupted(*args, **kwargs):
            calls.append(None)
            if len(calls) == 2:
                raise ValueError('SYNTHETIC_SECOND_PREDICTION_INTERRUPTION')
            return original(*args, **kwargs)
        kernel = self.product.kernel
        with patch.object(memory, 'record_prediction', side_effect=interrupted):
            with self.assertRaisesRegex(ValueError, 'SYNTHETIC_SECOND_PREDICTION_INTERRUPTION'):
                kernel.execute('prediction', 'persist', self.match_id, run_id='partial-after-one')
        replay = kernel.execute('prediction', 'persist', self.match_id, run_id='partial-after-one')
        self.assertEqual(replay['status'], 'partial')
        self.assertFalse(replay['available'])
        self.assertEqual(len(replay['predictions']), 1)
        observation = kernel.registry.item('prediction')['observation']
        self.assertNotEqual(observation['state'], 'READY')
        self.assertNotEqual(observation['last_operation']['state'], 'READY')

    def test_ensemble_is_scored_readonly_but_not_persisted_as_supported_base_evaluation(self):
        self.forecast('fictional-five-output-forecast')
        later = self.initial+timedelta(days=9)
        stamp = later.isoformat().replace('+00:00', 'Z')
        class LaterDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return later.astimezone(tz) if tz else later.replace(tzinfo=None)
        self.document['matches'][-2]['score'] = {'ft': [2, 1]}
        self.clock[0] = stamp
        with patch.object(public_results, '_now', return_value=stamp), \
             patch.object(memory, '_now', return_value=stamp), \
             patch.object(evaluation, 'datetime', LaterDatetime):
            self.ingest('fictional-later-result')
            result = self.evaluate('fictional-supported-base-evaluation')
        self.assertTrue(result['available'])
        self.assertEqual({group['model_name'] for group in result['history']['operational']['groups']},
                         set(models.NAMES)|{'ensemble'})
        stored = result['history']['records']['evaluations']
        self.assertEqual({row['model'] for row in stored}, set(models.NAMES))
        self.assertEqual(len(stored), 2*len(models.NAMES))
        self.assertNotIn('ensemble', {row['model'] for row in stored})


if __name__ == '__main__':
    unittest.main()
