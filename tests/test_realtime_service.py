"""Composed synthetic engine checks with real disposable storage and denied network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dragonhydra.realtime.bridge import VirtualResponsesTransport
from dragonhydra.realtime.events import instant
from dragonhydra.realtime.replay import standard_fixture
from dragonhydra.realtime.service import RealtimeService


class RecordingVirtualTransport(VirtualResponsesTransport):
    def __init__(self):
        self.calls = 0

    def create(self, request):
        self.calls += 1
        return super().create(request)


class RealtimeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dragonhydra-virtual-service-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        network.start()
        self.addCleanup(network.stop)
        self.services = []
        self.addCleanup(self.close_services)

    def close_services(self):
        for service in reversed(self.services):
            service.close()

    def service(self, name='research', **config):
        service = RealtimeService(self.root / name, {'auto_investigate': False, **config})
        self.services.append(service)
        return service

    def scenario(self, service):
        return service.create_scenario()['match_id']

    def step(self, service, match_id, steps=100):
        return service.replay_control(match_id, 'step', steps=steps)

    def finish(self, service, match_id):
        for _ in range(4):
            current = self.step(service, match_id)
            if current['replay']['status'] == 'COMPLETED':
                return current
        self.fail('Bounded virtual branch did not complete')

    def assert_clean_primary_sequence(self, service, match_id):
        state = service.store.state(match_id)
        primary = state['primary_source_id']
        rows = [event for event in service.events(match_id, 1000)['items'] if event['source_id'] == primary]
        sequences = sorted({event['sequence'] for event in rows})
        self.assertEqual(sequences, list(range(sequences[0], sequences[-1] + 1)))
        self.assertNotIn('MISSING_SEQUENCE', state['quality']['flags'])
        self.assertNotIn('PROVIDER_CLOCK_REGRESSION', state['quality']['flags'])

    def test_passive_views_expose_no_future_fixture_or_hidden_work(self):
        service = self.service()
        match_id = self.scenario(service)
        before = hashlib.sha256(service.store.path.read_bytes()).hexdigest()
        state = service.match(match_id)
        self.assertEqual(state['state']['revision'], 0)
        self.assertIsNone(state['current_forecast'])
        self.assertFalse(state['replay']['future_fixture_exposed'])
        self.assertNotIn('fixture', state['replay'])
        self.assertEqual(service.events(match_id)['items'], [])
        self.assertEqual(service.timeline(match_id)['items'], [])
        self.assertEqual(len(service.tools()['items']), 9)
        self.assertEqual(service.status()['metrics']['real_network_calls'], 0)
        self.assertEqual(hashlib.sha256(service.store.path.read_bytes()).hexdigest(), before)

    def test_complete_standard_replay_has_honest_forecasts_and_one_episode(self):
        service = self.service()
        match_id = self.scenario(service)
        state = self.step(service, match_id)
        self.assertEqual(state['state']['score'], {'home': 0, 'away': 1})
        self.assertEqual(state['state']['red_cards'], {'home': 0, 'away': 0})
        self.assertEqual(state['replay']['status'], 'COMPLETED')
        timeline = service.timeline(match_id)['items']
        self.assertGreater(len(timeline), 5)
        for wrapper in timeline:
            vector = wrapper['forecast']['full_time_result']
            if vector is not None:
                self.assertAlmostEqual(sum(vector.values()), 1., places=12)
                self.assertTrue(all(0 <= value <= 1 for value in vector.values()))
            self.assertEqual(wrapper['forecast']['model_status'], 'EXPERIMENTAL')
            self.assertEqual(wrapper['forecast']['calibration_state'], 'UNVERIFIED')
        report = service.evaluate()
        self.assertEqual(report['metrics']['sample_count'], 1)
        self.assertEqual(report['metrics']['independent_match_count'], 1)
        self.assertEqual(report['real_sporting_cases'], 0)
        self.assertFalse(report['metrics']['real_calibration_claim'])
        self.assertEqual(report['baseline_vs_assisted']['brier_delta'], 0.)
        self.assertFalse(report['baseline_vs_assisted']['quality_improvement_claim'])

    def test_optimized_and_forced_baseline_have_same_vectors_with_fewer_calculations(self):
        optimized = self.service('optimized')
        baseline = self.service('baseline', force_recompute=True)
        optimized_id, baseline_id = self.scenario(optimized), self.scenario(baseline)
        self.step(optimized, optimized_id)
        self.step(baseline, baseline_id)
        left = {w['state_revision']: w['forecast']['full_time_result'] for w in optimized.timeline(optimized_id)['items']}
        right = {w['state_revision']: w['forecast']['full_time_result'] for w in baseline.timeline(baseline_id)['items']}
        self.assertLess(len(left), len(right))
        self.assertTrue(left.keys() <= right.keys())
        self.assertTrue(all(vector == right[revision] for revision, vector in left.items()))
        self.assertGreater(optimized.store.metrics()['expensive_calculations_avoided'], 0)
        self.assertEqual(baseline.store.metrics().get('expensive_calculations_avoided', 0), 0)

    def test_real_bridge_result_and_budget_survive_restart_without_reexecution(self):
        transport = RecordingVirtualTransport()
        service = self.service(bridge={'transport': transport})
        match_id = self.scenario(service)
        self.step(service, match_id, 5)
        first = service.investigate(match_id)
        self.assertEqual(first['status'], 'completed', first)
        self.assertEqual((first['rounds'], first['tool_call_count']), (2, 4))
        self.assertEqual(transport.calls, 2)
        exported = service.bridge.export_state()
        service.close()
        restarted_transport = RecordingVirtualTransport()
        restarted = self.service(bridge={'transport': restarted_transport})
        second = restarted.investigate(match_id)
        self.assertEqual(second['analysis_id'], first['analysis_id'])
        self.assertEqual(restarted_transport.calls, 0)
        self.assertEqual(restarted.bridge.export_state(), exported)

    def test_unresolved_request_intent_is_never_automatically_replayed(self):
        service = self.service()
        match_id = self.scenario(service)
        self.step(service, match_id, 5)
        with patch.object(service.bridge, 'investigate', side_effect=RuntimeError('synthetic process interruption')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic process interruption'):
                service.investigate(match_id)
        service.close()
        transport = RecordingVirtualTransport()
        restarted = self.service(bridge={'transport': transport})
        result = restarted.investigate(match_id)
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertEqual(transport.calls, 0)
        self.assertEqual(restarted.store.analyses(match_id), [])

    def test_restart_recovers_accepted_state_after_failed_calculation(self):
        service = self.service()
        match_id = self.scenario(service)
        raw = standard_fixture(match_id)[0]
        with patch('dragonhydra.realtime.service.predict', side_effect=RuntimeError('synthetic interrupted calculation')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic interrupted calculation'):
                service.ingest(raw)
        self.assertEqual(service.store.state(match_id)['revision'], 1)
        self.assertIsNone(service.store.current_forecast(match_id))
        self.assertEqual(service.status()['metrics']['queue_depth'], 0)
        service.close()
        restarted = self.service()
        current = restarted.store.current_forecast(match_id)
        self.assertEqual(current['state_revision'], 1)
        self.assertIn('RECOVERED_ACCEPTED_STATE', current['change']['reason_codes'])
        self.assertEqual(restarted.store.metrics()['events_accepted'], 1)
        self.assertEqual(restarted.store.analyses(match_id), [])

    def test_corrupt_math_results_are_never_persisted_as_valid_forecasts(self):
        from dragonhydra.realtime.service import predict
        def corrupt(result, kind):
            if kind == 'nonfinite':
                result['full_time_result']['home'] = float('nan')
            elif kind == 'wrong_sum':
                result['full_time_result']['home'] = .99
            elif kind == 'unsupported_horizon':
                result['horizons']['7'] = result['horizons'].pop('5')
            elif kind == 'wrong_next_goal_sum':
                result['horizons']['5']['next_goal_side'].update(home=.5, away=.5, no_goal=.5)
            else:
                result['horizons']['5']['remaining_goals']['distribution'] = [1., 1.]
            return result
        for kind in ('nonfinite', 'wrong_sum', 'unsupported_horizon', 'wrong_next_goal_sum', 'wrong_goal_count_sum'):
            with self.subTest(kind=kind):
                service = self.service('corrupt-' + kind)
                match_id = self.scenario(service)
                def invalid_math(state, config=None):
                    return corrupt(predict(state, config), kind)
                with patch('dragonhydra.realtime.service.predict', side_effect=invalid_math):
                    with self.assertRaises(ValueError):
                        service.ingest(standard_fixture(match_id)[0])
                self.assertEqual(service.store.state(match_id)['revision'], 1)
                self.assertIsNone(service.store.current_forecast(match_id))
                self.assertEqual(service.timeline(match_id)['items'], [])
                self.assertEqual(service.status()['metrics']['queue_depth'], 0)

    def test_concurrent_duplicate_ingestion_computes_one_forecast(self):
        service = self.service()
        match_id = self.scenario(service)
        raw = standard_fixture(match_id)[0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(service.ingest, [deepcopy(raw) for _ in range(24)]))
        self.assertEqual(sum(row['decision']['action'] != 'DUPLICATE' for row in results), 1)
        self.assertEqual(service.store.metrics()['forecast_updates'], 1)
        self.assertEqual(service.store.metrics()['duplicates_rejected'], 23)
        self.assertEqual(service.status()['metrics']['queue_depth'], 0)

    def test_backpressure_refuses_second_event_before_journal_mutation(self):
        service = self.service(max_pending=1)
        match_id = self.scenario(service)
        fixture = standard_fixture(match_id)
        entered, release = threading.Event(), threading.Event()
        from dragonhydra.realtime.service import predict
        def slow(state, config=None):
            entered.set()
            if not release.wait(2):
                raise AssertionError('Test did not release synthetic calculation')
            return predict(state, config)
        with patch('dragonhydra.realtime.service.predict', side_effect=slow), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.ingest, fixture[0])
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaisesRegex(ValueError, 'RESEARCH_BACKPRESSURE'):
                    service.ingest(fixture[1])
                self.assertEqual(len(service.store.events(match_id)), 1)
            finally:
                release.set()
                future.result(timeout=2)
        self.assertEqual(service.store.metrics()['backpressure_rejections'], 1)
        self.assertEqual(service.status()['metrics']['queue_depth'], 0)

    def test_historical_tool_context_has_no_future_labels_or_analysis(self):
        service = self.service()
        match_id = self.scenario(service)
        self.step(service, match_id)
        service.evaluate()
        pre_final = service.store.timeline(match_id)[-2]
        later_analysis = service.investigate(match_id, pre_final['revision'])
        self.assertEqual(later_analysis['status'], 'completed', later_analysis)
        final_revision = service.store.state(match_id)['revision']
        early = service._context(match_id, 1)
        self.assertEqual(early['state']['revision'], 1)
        self.assertEqual(len(early['events']), 1)
        self.assertTrue(all(w['state_revision'] <= 1 for w in early['timeline']))
        self.assertTrue(early['calibration_report'] is None, 'Historical context exposed a later outcome-derived report')
        self.assertEqual(early['analyses'], [])
        self.assertNotIn('FULL_TIME', {row['event_type'] for row in early['events']})
        self.assertGreater(final_revision, 1)

    def test_branch_preserves_original_history_and_inherits_only_accepted_prefix(self):
        service = self.service()
        match_id = self.scenario(service)
        self.step(service, match_id, 6)
        parent_before = json.dumps(service.timeline(match_id), sort_keys=True)
        parent_events = deepcopy(service.events(match_id))
        child = service.branch(match_id, 4, branch_name='virtual-test-fork', seed=73)
        child_id = child['match_id']
        self.assertNotEqual(child_id, match_id)
        self.assertEqual(service.store.state(child_id)['score'], service.store.state(match_id, 4)['score'])
        self.assertEqual(len(service.events(child_id)['items']), 4)
        self.assertTrue(all(e['match_id'] == child_id for e in service.events(child_id)['items']))
        self.assertEqual(json.dumps(service.timeline(match_id), sort_keys=True), parent_before)
        self.assertEqual(service.events(match_id), parent_events)
        self.assertFalse(service.match(child_id)['replay']['future_fixture_exposed'])

    def test_counterfactual_tools_use_the_primary_forecasts_trusted_configuration(self):
        service = self.service(model={'home_rate': .5, 'away_rate': 2.5})
        match_id = self.scenario(service)
        self.step(service, match_id, 5)
        expected = service.match(match_id)['current_forecast']['forecast']['full_time_result']
        result = service.investigate(match_id)
        self.assertEqual(result['status'], 'completed', result)
        comparison = next(row['result'] for row in result['tool_results'] if row['tool'] == 'compare_model_predictions')
        self.assertEqual(comparison['models'][0]['full_time_result'], expected)
        counterfactual = next(row['result'] for row in result['tool_results'] if row['tool'] == 'run_bounded_counterfactual')
        self.assertEqual(counterfactual['baseline']['full_time_result'], expected)

    def test_final_score_cannot_be_changed_by_an_unversioned_post_final_goal(self):
        service = self.service()
        match_id = self.scenario(service)
        self.step(service, match_id)
        before = service.store.state(match_id)
        raw = deepcopy(standard_fixture(match_id)[-1])
        raw.update(event_id='virtual-after-final', event_type='GOAL', sequence=19, participant='HOME')
        raw['attributes'] = {'minute': 96}
        raw['event_time'] = '2035-01-01T13:36:00Z'
        raw['received_at'] = '2035-01-01T13:36:02Z'
        try:
            service.ingest(raw)
        except ValueError:
            pass  # Rejection or a recorded non-mutating quarantine is acceptable.
        after = service.store.state(match_id)
        self.assertEqual(after['status'], 'FINISHED')
        self.assertEqual(after['score'], before['score'])

    def test_process_restart_pauses_retained_playing_control_without_replay(self):
        service = self.service()
        match_id = self.scenario(service)
        controls = service.store.get_replay(match_id)
        controls['status'] = 'PLAYING'  # Disposable crash fixture: previous worker no longer exists.
        service.store.set_replay(match_id, controls)
        service.close()
        restarted = self.service()
        current = restarted.match(match_id)
        self.assertEqual(current['replay']['status'], 'PAUSED')
        self.assertEqual(current['replay']['reason'], 'PROCESS_RESTARTED')
        self.assertEqual(current['state']['revision'], 0)
        self.assertEqual(restarted.events(match_id)['items'], [])

    def test_half_time_and_suspended_branches_resume_before_future_observations(self):
        for mode in ('HALF_TIME', 'SUSPENDED'):
            with self.subTest(mode=mode):
                service = self.service('resume-branch-' + mode)
                parent = self.scenario(service)
                self.step(service, parent, 8 if mode == 'HALF_TIME' else 5)
                if mode == 'SUSPENDED':
                    suspended = deepcopy(standard_fixture(parent)[0])
                    suspended.update(event_id='virtual-parent-suspension', event_type='SUSPEND', sequence=5)
                    suspended['attributes'] = {'minute': 20}
                    suspended['event_time'] = '2035-01-01T12:20:00Z'
                    suspended['received_at'] = '2035-01-01T12:20:02Z'
                    service.ingest(suspended)
                inherited = service.store.state(parent)
                self.assertEqual(inherited['status'], mode)
                before_timeline = deepcopy(service.timeline(parent))
                before_events = deepcopy(service.events(parent))
                child = service.branch(parent, inherited['revision'], branch_name='virtual-resume-' + mode, seed=73)['match_id']
                first = self.step(service, child, 1)
                resumed = service.events(child, 1000)['items'][-1]
                self.assertEqual(resumed['event_type'], 'RESUME')
                self.assertEqual(first['state']['status'], 'IN_PLAY')
                self.assertEqual(first['state']['minute'], inherited['minute'])
                self.assertEqual(first['state']['period'], 2 if mode == 'HALF_TIME' else inherited['period'])
                self.assertGreater(instant(resumed['event_time']), instant(inherited['received_at']))
                self.finish(service, child)
                self.assert_clean_primary_sequence(service, child)
                self.assertEqual(service.timeline(parent), before_timeline)
                self.assertEqual(service.events(parent), before_events)
                self.assertEqual(service.store.state(parent), inherited)

    def test_branch_keeps_known_second_half_stoppage_and_never_finishes_at_ninety(self):
        service = self.service()
        parent = self.scenario(service)
        self.step(service, parent, 16)
        inherited = service.store.state(parent)
        self.assertEqual((inherited['minute'], inherited['period_end_minute']), (89., 95))
        before = deepcopy(service.timeline(parent)), deepcopy(service.events(parent)), deepcopy(inherited)
        child = service.branch(parent, inherited['revision'], branch_name='virtual-stoppage-fork', seed=29)['match_id']
        completed = self.finish(service, child)
        self.assertEqual(completed['state']['status'], 'FINISHED')
        self.assertGreaterEqual(completed['state']['minute'], 95)
        self.assertGreaterEqual(completed['state']['period_end_minute'], 95)
        all_events = service.events(child, 1000)['items']
        future = all_events[len(before[1]['items']):]
        self.assertTrue(future)
        final = [row for row in future if row['event_type'] == 'FULL_TIME']
        self.assertEqual(len(final), 1)
        self.assertGreaterEqual(final[0]['attributes']['minute'], 95)
        for row in future:
            if row['attributes'].get('period') == 2 and 'period_end_minute' in row['attributes']:
                self.assertGreaterEqual(row['attributes']['period_end_minute'], 95)
            self.assertGreater(instant(row['event_time']), instant(inherited['received_at']))
        self.assert_clean_primary_sequence(service, child)
        self.assertEqual((service.timeline(parent), service.events(parent), service.store.state(parent)), before)

    def test_malformed_branch_seed_or_universe_has_no_match_or_evidence_side_effect(self):
        service = self.service()
        parent = self.scenario(service)
        self.step(service, parent, 5)
        before = deepcopy(service.matches()), deepcopy(service.timeline(parent)), deepcopy(service.events(parent)), deepcopy(service.store.metrics())
        for seed in (True, -1, 2 ** 32, '42', 10 ** 999):
            with self.subTest(seed=str(seed)[:20]), self.assertRaises(ValueError):
                service.branch(parent, 1, branch_name='virtual-invalid-seed', seed=seed)
            self.assertEqual((service.matches(), service.timeline(parent), service.events(parent), service.store.metrics()), before)
        for universe in ('not-a-universe', None, []):
            with self.subTest(universe=universe), self.assertRaises(ValueError):
                service.branch(parent, 1, branch_name='virtual-invalid-universe', universe=universe)
            self.assertEqual((service.matches(), service.timeline(parent), service.events(parent), service.store.metrics()), before)

    def test_shutdown_and_invalid_config_fail_closed(self):
        service = self.service()
        match_id = self.scenario(service)
        service.close()
        with self.assertRaisesRegex(ValueError, 'RESEARCH_ENGINE_CLOSED'):
            service.ingest(standard_fixture(match_id)[0])
        for config in ({'unknown': True}, {'max_pending': 0}, {'auto_investigate': 1},
                       {'bridge': {'state': {}}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.service('invalid-' + str(len(self.services)), **config)


if __name__ == '__main__':
    unittest.main()
