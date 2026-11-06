"""Distinct-event races and irrelevant-event storms over owned virtual SQLite."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dragonhydra.realtime.bridge import VIRTUAL_CREDENTIAL, VirtualResponsesTransport
from dragonhydra.realtime.events import instant
from dragonhydra.realtime.replay import EPOCH, standard_fixture
from dragonhydra.realtime.service import RealtimeService


class RecordingVirtualTransport(VirtualResponsesTransport):
    def __init__(self):
        self.calls = 0

    def create(self, request):
        self.calls += 1
        return super().create(request)


class RealtimeAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='genesis6-virtual-adversarial-')
        self.addCleanup(self.temp.cleanup)
        network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def service(self, **config):
        service = RealtimeService(Path(self.temp.name) / 'owned-research', config)
        self.addCleanup(service.close)
        match_id = service.create_scenario()['match_id']
        kickoff = standard_fixture(match_id)[0]
        service.ingest(kickoff)
        return service, match_id, kickoff

    @staticmethod
    def observation(kickoff, kind, sequence, participant='NONE', **attributes):
        event = deepcopy(kickoff)
        event.update(event_id='virtual-adversarial-' + kind.lower() + '-' + str(sequence),
                     event_type=kind, sequence=sequence, participant=participant)
        event['attributes'] = {'minute': 10, **attributes}
        at = EPOCH + timedelta(minutes=10)
        event['event_time'] = at.isoformat().replace('+00:00', 'Z')
        event['received_at'] = (at + timedelta(seconds=2)).isoformat().replace('+00:00', 'Z')
        return event

    def test_concurrent_distinct_goal_and_card_preserve_both_facts_and_prefix(self):
        service, match_id, kickoff = self.service(auto_investigate=False)
        prefix_event = deepcopy(service.events(match_id)['items'][0])
        prefix_state = deepcopy(service.store.state(match_id, 1))
        prefix_forecast = json.dumps(service.timeline(match_id)['items'][0], sort_keys=True)
        goal = self.observation(kickoff, 'GOAL', 2, 'HOME')
        card = self.observation(kickoff, 'RED_CARD', 3, 'AWAY')
        ready = threading.Barrier(3)
        def ingest(raw):
            ready.wait(timeout=3)
            return service.ingest(raw)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ingest, raw) for raw in (goal, card)]
            ready.wait(timeout=3)
            receipts = [future.result(timeout=5) for future in futures]
        self.assertTrue(all(row['decision']['action'] != 'DUPLICATE' for row in receipts))
        state = service.store.state(match_id)
        self.assertEqual(state['revision'], 3)
        self.assertEqual(state['score'], {'home': 1, 'away': 0})
        self.assertEqual(state['red_cards'], {'home': 0, 'away': 1})
        self.assertNotIn('MISSING_SEQUENCE', state['quality']['flags'])
        accepted = service.events(match_id)['items']
        self.assertEqual(len(accepted), 3)
        self.assertEqual({row['event_id'] for row in accepted[1:]}, {goal['event_id'], card['event_id']})
        self.assertEqual(accepted[0], prefix_event)
        self.assertEqual(service.store.state(match_id, 1), prefix_state)
        self.assertEqual(json.dumps(service.timeline(match_id)['items'][0], sort_keys=True), prefix_forecast)
        current = service.match(match_id)['current_forecast']
        self.assertEqual(current['state_revision'], 3)
        vector = current['forecast']['full_time_result']
        self.assertAlmostEqual(sum(vector.values()), 1., places=12)
        self.assertTrue(all(0 <= value <= 1 for value in vector.values()))

    def test_irrelevant_event_storm_adds_no_automatic_analysis_or_forecast(self):
        transport = RecordingVirtualTransport()
        service, match_id, kickoff = self.service(auto_investigate=True,
                                                 bridge={'transport': transport, 'credential': VIRTUAL_CREDENTIAL})
        self.assertEqual(service.store.analyses(match_id), [])
        goal = self.observation(kickoff, 'GOAL', 2, 'HOME')
        service.ingest(goal)
        analyses = deepcopy(service.store.analyses(match_id))
        self.assertEqual(len(analyses), 1)
        self.assertEqual(analyses[0]['status'], 'completed')
        self.assertEqual(analyses[0]['tool_call_count'], 4)
        self.assertEqual(analyses[0]['rounds'], 2)
        self.assertEqual(transport.calls, 2)
        before_forecasts = deepcopy(service.timeline(match_id))
        before_current = deepcopy(service.store.current_forecast(match_id))
        before_metrics = service.store.metrics()
        irrelevant = []
        for index in range(100):
            raw = self.observation(kickoff, 'POSSESSION', index + 3, home_percent=30 + index % 41)
            irrelevant.append(raw)
            receipt = service.ingest(raw)
            self.assertEqual(receipt['decision']['action'], 'STATE_ONLY')
        for raw in irrelevant[:20]:
            duplicate = deepcopy(raw)
            duplicate['received_at'] = (instant(raw['received_at']) + timedelta(seconds=3)).isoformat().replace('+00:00', 'Z')
            self.assertEqual(service.ingest(duplicate)['decision']['action'], 'DUPLICATE')
        metrics = service.store.metrics()
        self.assertEqual(metrics['events_accepted'], 102)
        self.assertEqual(metrics['duplicates_rejected'], 20)
        self.assertEqual(metrics['expensive_calculations_avoided'] - before_metrics.get('expensive_calculations_avoided', 0), 100)
        self.assertEqual(metrics['forecast_updates'], before_metrics['forecast_updates'])
        self.assertEqual(metrics['ai_investigations'], before_metrics['ai_investigations'])
        self.assertEqual(service.store.analyses(match_id), analyses)
        self.assertEqual(service.store.current_forecast(match_id), before_current)
        self.assertEqual(service.timeline(match_id), before_forecasts)
        self.assertEqual(transport.calls, 2)
        self.assertEqual(service.status()['metrics']['real_network_calls'], 0)


if __name__ == '__main__':
    unittest.main()
