"""Virtual Responses loop integration, budgets and hostile-output checks; all network denied."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import threading
import unittest
from unittest.mock import patch

from dragonhydra.realtime import models
from dragonhydra.realtime.bridge import (ANALYSIS_FORMAT, NeuralBridge, TOOLS,
                                         VirtualResponsesTransport, tool_schemas, validate_packet)
from dragonhydra.realtime.events import initial_state
from dragonhydra.realtime.evaluation import evaluate_forecasts


def fixture():
    state = initial_state('virtual-bridge-match')
    state.update(status='IN_PLAY', minute=20., revision=1)
    state['quality'] = {'status': 'VALIDATED', 'flags': []}
    state['virtual_historical_analogues'] = [{'synthetic': True, 'analogue_id': 'virtual-analogue-1',
                                             'description': 'Synthetic configured example only.'}]
    forecast = models.predict(state)
    event = {'event_id': 'virtual-event-1', 'source_id': 'virtual-source-1', 'match_id': state['match_id'],
             'event_type': 'CLOCK', 'attributes': {'minute': 20.}, 'source_mode': 'DEMONSTRATION'}
    wrapper = {'forecast_id': 'forecast:virtual-1', 'forecast': forecast}
    report = evaluate_forecasts(
        [{'prediction_id': 'virtual-calibration-prediction', 'match_id': 'virtual-calibration-episode',
          'forecast_target': 'goal_occurrence', 'horizon': 5, 'probabilities': {'goal': .25, 'no_goal': .75},
          'decision_at': '2034-01-01T12:00:00Z', 'available_at': '2034-01-01T12:00:00Z',
          'source_mode': 'DEMONSTRATION', 'synthetic': True}],
        [{'match_id': 'virtual-calibration-episode', 'forecast_target': 'goal_occurrence', 'horizon': 5,
          'label': 'goal', 'occurred_at': '2034-01-01T12:05:00Z', 'available_at': '2034-01-01T12:05:01Z',
          'source_mode': 'DEMONSTRATION', 'synthetic': True}], cutoff='2034-01-01T13:00:00Z')
    context = {'state': state, 'current_forecast': wrapper, 'timeline': [wrapper],
               'events': [event], 'analyses': [], 'calibration_report': report}
    packet = {'schema_version': 'dragonhydra.neural-packet/1', 'packet_id': 'virtual-packet-1',
              'match_id': state['match_id'], 'event_revision': 1, 'source_mode': 'DEMONSTRATION',
              'forecast_target': 'full_time_result',
              'event': {'event_id': event['event_id'], 'type': 'CLOCK', 'minute': 20.},
              'observed_score': {'home': 0, 'away': 0},
              'probability_before': forecast['full_time_result'], 'probability_after': forecast['full_time_result'],
              'change': {'home': 0., 'draw': 0., 'away': 0.},
              'data_quality': {'status': 'VALIDATED', 'flags': []}, 'model_id': forecast['model_id'],
              'evidence_ids': [event['event_id'], wrapper['forecast_id']],
              'investigation': {'reason': 'virtual-clock-change', 'question': 'Which configured assumptions matter?'}}
    return context, deepcopy(packet)


class RecordingTransport(VirtualResponsesTransport):
    def __init__(self, mutate=None):
        self.requests = []
        self.mutate = mutate

    def create(self, request):
        self.requests.append(deepcopy(request))
        result = super().create(request)
        return self.mutate(result, len(self.requests)) if self.mutate else result


def final_analysis(evidence, call_id='virtual-math'):
    return {'summary': 'Synthetic tools were checked.',
            'observed_facts': [{'statement': 'The evidence belongs to a simulation.',
                               'evidence_ids': evidence, 'classification': 'OBSERVED_FACT_IN_SIMULATION'}],
            'mathematical_findings': [{'statement': 'Configured model variants were computed.',
                                       'tool_call_id': call_id, 'evidence_ids': evidence,
                                       'classification': 'DETERMINISTIC_MATH'}],
            'hypotheses': [{'statement': 'The configured assumptions may explain the movement.',
                            'confidence': 'low', 'evidence_ids': evidence, 'classification': 'AI_HYPOTHESIS'}],
            'evidence_ids': evidence, 'limitations': ['Synthetic demonstration; real calibration is unverified.']}


def message(analysis):
    return {'output': [{'type': 'message', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': json.dumps(analysis)}]}], 'usage': None}


class RealtimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.context, self.packet = fixture()
        self.before = deepcopy(self.context)
        self.network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def bridge(self, transport=None, **config):
        return NeuralBridge(lambda _: self.context,
                            {'clock': lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
                             **({'transport': transport} if transport is not None else {}), **config})

    def test_default_reasoner_consumes_actual_math_without_forecast_mutation(self):
        transport = RecordingTransport()
        result = self.bridge(transport).investigate(self.packet)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual((result['rounds'], result['tool_call_count']), (2, 4))
        self.assertEqual(result['real_network_call_count'], 0)
        self.assertIsNone(result['usage'])
        self.assertIsNone(result['cost'])
        self.assertFalse(result['probabilities_changed'])
        tools = {row['tool']: row for row in result['tool_results']}
        self.assertEqual(len(tools['compare_model_predictions']['result']['models']), 3)
        delta = tools['run_bounded_counterfactual']['result']['full_time_result_delta']
        self.assertTrue(any(abs(number) > 1e-10 for number in delta.values()))
        self.assertIn('changed the deterministic forecast', result['analysis']['mathematical_findings'][1]['statement'])
        self.assertEqual(self.context, self.before)
        self.assertEqual(result['classification'], 'AI_HYPOTHESIS')

    def test_responses_wire_shape_reasoning_preserved_before_outputs(self):
        transport = RecordingTransport()
        self.bridge(transport).investigate(self.packet)
        first, second = transport.requests
        self.assertIs(first['store'], False)
        self.assertIs(first['parallel_tool_calls'], True)
        self.assertNotIn('response_format', first)
        self.assertEqual(first['text']['format']['schema'], ANALYSIS_FORMAT)
        detached = tool_schemas()
        detached[0]['name'] = 'virtual-untrusted-change'
        self.assertNotEqual(detached[0]['name'], tool_schemas()[0]['name'])
        for tool in first['tools']:
            self.assertNotIn('function', tool)
            self.assertTrue(tool['strict'])
            self.assertFalse(tool['parameters']['additionalProperties'])
            self.assertEqual(set(tool['parameters']['required']), set(tool['parameters']['properties']))
        types = [item.get('type') for item in second['input']]
        self.assertLess(types.index('reasoning'), types.index('function_call_output'))
        for output in (item for item in second['input'] if item.get('type') == 'function_call_output'):
            self.assertEqual(set(output), {'type', 'call_id', 'output'})
            self.assertTrue(json.loads(output['output'])['synthetic'])

    def test_all_nine_handlers_are_real_bounded_readers_or_calculators(self):
        cases = [('get_current_match_state', {}), ('get_forecast_distribution', {}), ('get_data_quality_report', {}),
                 ('get_recent_event_history', {'limit': 1}), ('get_historical_analogues', {'limit': 1}),
                 ('get_calibration_report', {}), ('get_prediction_evidence', {'evidence_ids': self.packet['evidence_ids']}),
                 ('run_bounded_counterfactual', {'minute_advance': 1, 'score_delta': {'home': 1, 'away': 0},
                                         'red_card_delta': {'home': 0, 'away': 1}})]
        self.assertEqual(len(TOOLS), 9)
        for index, (name, arguments) in enumerate(cases):
            class ToolReasoner:
                virtual_only = True
                def create(inner, request):
                    if any(item.get('type') == 'function_call_output' for item in request['input']):
                        return message(final_analysis(self.packet['evidence_ids']))
                    return {'output': [{'type': 'function_call', 'call_id': 'virtual-math', 'name': 'compare_model_predictions',
                                        'arguments': json.dumps({'match_id': self.packet['match_id']})},
                                       {'type': 'function_call', 'call_id': 'virtual-reader', 'name': name,
                                        'arguments': json.dumps({'match_id': self.packet['match_id']} | arguments)}], 'usage': None}
            with self.subTest(name=name):
                result = self.bridge(ToolReasoner()).investigate(self.packet | {'packet_id': 'virtual-packet-' + str(index)})
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(result['tool_results'][-1]['tool'], name)
                if name == 'run_bounded_counterfactual':
                    changed = result['tool_results'][-1]['result']['changed_state']
                    self.assertEqual(changed['score']['home'], 1)
                    self.assertEqual(changed['red_cards']['away'], 1)
                elif name == 'get_calibration_report':
                    self.assertEqual(result['tool_results'][-1]['result']['sample_count'], 1)
                    self.assertEqual(result['tool_results'][-1]['result']['brier_score'], 1.125)
                elif name == 'get_historical_analogues':
                    self.assertEqual(len(result['tool_results'][-1]['result']), 1)
                    self.assertTrue(result['tool_results'][-1]['result'][0]['synthetic'])
        self.assertEqual(self.context, self.before)

    def test_dedup_survives_export_restore_and_rejects_changed_packet(self):
        transport = RecordingTransport()
        bridge = self.bridge(transport)
        first = bridge.investigate(self.packet)
        second = bridge.investigate(self.packet)
        self.assertTrue(second['cache_hit'])
        self.assertEqual(first['analysis_id'], second['analysis_id'])
        self.assertEqual(len(transport.requests), 2)
        restored = self.bridge(transport, state=json.loads(json.dumps(bridge.export_state())))
        self.assertTrue(restored.investigate(self.packet)['cache_hit'])
        changed = deepcopy(self.packet)
        changed['investigation']['question'] = 'Changed question.'
        with self.assertRaisesRegex(ValueError, 'PACKET_ID_REUSED'):
            restored.investigate(changed)

    def test_match_and_daily_budgets_apply_before_any_transport(self):
        transport = RecordingTransport()
        bridge = self.bridge(transport, per_match_limit=1, per_day_limit=1)
        bridge.investigate(self.packet)
        result = bridge.investigate(self.packet | {'packet_id': 'virtual-another'})
        self.assertEqual(result['reason'], 'DAILY_OR_MATCH_BUDGET')
        self.assertEqual(len(transport.requests), 2)

    def test_bad_credentials_and_real_transport_rejected_without_inspection(self):
        for credential in ('sk-proj-forbidden-test', '', 'anything-else'):
            with self.assertRaisesRegex(ValueError, 'VIRTUAL_CREDENTIAL_ONLY'):
                self.bridge(credential=credential)
        with self.assertRaisesRegex(ValueError, 'VIRTUAL_TRANSPORT_ONLY'):
            self.bridge(transport=object())

    def test_packet_nonfinite_size_duplicate_fields_and_delta_rejected(self):
        mutations = [self.packet | {'extra': 1}, self.packet | {'schema_version': 1},
                     self.packet | {'source_mode': 'LIVE'}, self.packet | {'match_id': 'real-record'},
                     self.packet | {'change': {'home': .1, 'draw': 0., 'away': 0.}},
                     self.packet | {'event_revision': 10 ** 999},
                     self.packet | {'probability_after': {'home': math.nan, 'draw': .5, 'away': .5}}]
        for packet in mutations:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                validate_packet(packet)
        with self.assertRaisesRegex(ValueError, 'JSON_SIZE_LIMIT'):
            validate_packet(' ' * 16385)
        encoded = json.dumps(self.packet)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_FIELD'):
            validate_packet(encoded[:-1] + ',"packet_id":"virtual-other"}')

    def test_context_identity_revision_forecast_and_evidence_must_match(self):
        mutations = [('synthetic', False), ('match_id', 'virtual-other'), ('revision', 2)]
        for field, value in mutations:
            with self.subTest(field=field):
                context = deepcopy(self.context)
                context['state'][field] = value
                transport = RecordingTransport()
                result = NeuralBridge(lambda _: context, {'transport': transport}).investigate(self.packet)
                self.assertEqual(result['status'], 'uncertain')
                self.assertEqual(transport.requests, [])
        bad = self.packet | {'evidence_ids': ['virtual-invented']}
        self.assertEqual(self.bridge().investigate(bad)['reason'], 'INVENTED_EVIDENCE_ID')
        bad = self.packet | {'model_id': 'invented-model'}
        self.assertEqual(self.bridge().investigate(bad)['reason'], 'PACKET_CONTEXT_FORECAST_MISMATCH')
        mismatched = deepcopy(self.context)
        mismatched['current_forecast']['forecast']['model_configuration'] = {'home_rate': .5}
        mismatched['model_config'] = {'home_rate': 2.}
        self.assertEqual(NeuralBridge(lambda _: mismatched).investigate(self.packet)['reason'],
                         'MODEL_CONFIGURATION_BINDING_MISMATCH')
        for error in (ValueError, RuntimeError):
            def broken_context(_):
                raise error('untrusted private diagnostic payload')
            redacted = NeuralBridge(broken_context).investigate(self.packet)
            self.assertEqual(redacted['reason'], 'VIRTUAL_CONTEXT_OR_TOOL_FAILED')
            self.assertNotIn('untrusted private diagnostic payload', json.dumps(redacted))

    def test_unsupported_cross_match_extra_arg_and_duplicate_call_fail_closed(self):
        def change(result, count):
            if count == 1:
                result['output'][1]['name'] = 'execute_shell'
            return result
        self.assertEqual(self.bridge(RecordingTransport(change)).investigate(self.packet)['reason'], 'UNSUPPORTED_TOOL')
        for field, value, code in [('match_id', 'virtual-other', 'CROSS_MATCH_TOOL_REJECTED'),
                                   ('unexpected', True, 'UNEXPECTED_OR_MISSING_FIELDS')]:
            def mutate(result, count):
                if count == 1:
                    call = result['output'][1]
                    call['arguments'] = json.dumps(json.loads(call['arguments']) | {field: value})
                return result
            self.assertEqual(self.bridge(RecordingTransport(mutate)).investigate(self.packet)['reason'], code)
        def duplicate(result, count):
            if count == 1:
                result['output'][2]['call_id'] = result['output'][1]['call_id']
            return result
        self.assertEqual(self.bridge(RecordingTransport(duplicate)).investigate(self.packet)['reason'], 'DUPLICATE_TOOL_CALL_ID')

    def test_invented_final_evidence_probability_override_and_fake_usage_rejected(self):
        for field, value in [('evidence_ids', ['virtual-invented']), ('probabilities', {'home': 1.})]:
            def mutate(result, count):
                if count == 2:
                    text = result['output'][0]['content'][0]
                    text['text'] = json.dumps(json.loads(text['text']) | {field: value})
                return result
            self.assertEqual(self.bridge(RecordingTransport(mutate)).investigate(self.packet)['status'], 'uncertain')
        def usage(result, count):
            result['usage'] = {'total_tokens': 100}
            return result
        self.assertEqual(self.bridge(RecordingTransport(usage)).investigate(self.packet)['reason'], 'VIRTUAL_RESPONSE_SHAPE_INVALID')

    def test_tool_round_call_and_no_tool_final_budgets(self):
        self.assertEqual(self.bridge(max_rounds=1).investigate(self.packet)['reason'], 'TOOL_ROUND_BUDGET')
        self.assertEqual(self.bridge(max_tool_calls=3).investigate(self.packet)['reason'], 'TOOL_CALL_BUDGET_OR_MIXED_OUTPUT')
        class NoTools:
            virtual_only = True
            def create(inner, request):
                return message(final_analysis(self.packet['evidence_ids']))
        self.assertEqual(self.bridge(NoTools()).investigate(self.packet)['reason'], 'EVIDENCE_TOOLS_REQUIRED_BEFORE_ANALYSIS')

    def test_tool_boundaries_reject_oversized_read_and_counterfactual_requests(self):
        counterfactual = {'minute_advance': 1., 'score_delta': {'home': 0, 'away': 0},
                          'red_card_delta': {'home': 0, 'away': 0}}
        cases = [('get_recent_event_history', {'limit': 21}),
                 ('get_historical_analogues', {'limit': 6}),
                 ('get_recent_event_history', {'limit': 10 ** 999}),
                 ('run_bounded_counterfactual', counterfactual | {'minute_advance': 11.}),
                 ('run_bounded_counterfactual', counterfactual | {'score_delta': {'home': 2, 'away': 0}}),
                 ('run_bounded_counterfactual', counterfactual | {'red_card_delta': {'home': -1, 'away': 0}}),
                 ('get_prediction_evidence', {'evidence_ids': ['virtual-event-1'] * 33})]
        for name, arguments in cases:
            def mutate(result, count):
                if count == 1:
                    result['output'][1]['name'] = name
                    result['output'][1]['arguments'] = json.dumps({'match_id': self.packet['match_id']} | arguments)
                return result
            with self.subTest(tool=name, arguments=str(arguments)[:100]):
                transport = RecordingTransport(mutate)
                result = self.bridge(transport).investigate(self.packet)
                self.assertEqual(result['status'], 'uncertain')
                self.assertFalse(result['probabilities_changed'])
                self.assertEqual(len(transport.requests), 1)
        self.assertEqual(self.context, self.before)

    def test_timeout_uncertain_cached_no_retry_and_background_concurrency_blocked(self):
        release, finished = threading.Event(), threading.Event()
        class Slow:
            virtual_only = True
            calls = 0
            def create(inner, request):
                inner.calls += 1
                release.wait(.5)
                finished.set()
                return {'output': [], 'usage': None}
        slow = Slow()
        bridge = self.bridge(slow, timeout_seconds=.01)
        try:
            first = bridge.investigate(self.packet)
            self.assertEqual(first['reason'], 'VIRTUAL_CALL_TIMEOUT_UNCERTAIN_NO_RETRY')
            self.assertTrue(bridge.investigate(self.packet)['cache_hit'])
            self.assertEqual(bridge.investigate(self.packet | {'packet_id': 'virtual-another'})['reason'], 'CONCURRENCY_BUDGET')
            self.assertEqual(slow.calls, 1)
        finally:
            release.set()
            self.assertTrue(finished.wait(.5))

    def test_circuit_disabled_and_malformed_restored_state(self):
        transport = RecordingTransport(lambda result, _: {'output': [], 'usage': None})
        bridge = self.bridge(transport, circuit_failure_limit=1)
        bridge.investigate(self.packet)
        self.assertEqual(bridge.investigate(self.packet | {'packet_id': 'virtual-new'})['reason'], 'VIRTUAL_CIRCUIT_OPEN_NO_RETRY')
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(self.bridge(transport, enabled=False).investigate(self.packet)['status'], 'disabled')
        state = bridge.export_state()
        state['days']['2026-01-01']['total'] = -1
        with self.assertRaisesRegex(ValueError, 'INVALID_BRIDGE_STATE'):
            self.bridge(state=state)


if __name__ == '__main__':
    unittest.main()
