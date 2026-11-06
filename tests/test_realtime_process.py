"""Committed synthetic event survives an abrupt subprocess exit before forecast."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from dragonhydra.realtime.service import RealtimeService


class RealtimeProcessRecovery(unittest.TestCase):
    def test_committed_event_recovers_after_actual_process_exit(self):
        with tempfile.TemporaryDirectory(prefix='genesis6-crash-fixture-') as temporary:
            state = Path(temporary) / 'new-synthetic-state'
            program = r'''
import os, socket, sys
from dragonhydra.realtime.service import RealtimeService
from dragonhydra.realtime.replay import standard_fixture
def no_network(*args, **kwargs): raise AssertionError('NETWORK_FORBIDDEN')
socket.socket = no_network
service = RealtimeService(sys.argv[1], {'auto_investigate': False})
match_id = service.create_scenario()['match_id']
service.store.accept(standard_fixture(match_id)[0])
assert service.store.current_forecast(match_id) is None
os._exit(37)
'''
            environment = dict(os.environ)
            environment['PYTHONPATH'] = str(Path(__file__).absolute().parents[1] / 'src')
            environment['PYTHONDONTWRITEBYTECODE'] = '1'
            child = subprocess.run([sys.executable, '-B', '-c', program, str(state)],
                                   env=environment, capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 37, child.stderr)
            recovered = RealtimeService(state, {'auto_investigate': False})
            try:
                match = recovered.matches()['items'][0]
                mid = match['match_id']
                self.assertEqual(match['state']['revision'], 1)
                self.assertEqual(len(recovered.events(mid)['items']), 1)
                self.assertEqual(len(recovered.timeline(mid)['items']), 1)
                self.assertIn('RECOVERED_ACCEPTED_STATE', recovered.match(mid)['current_forecast']['change']['reason_codes'])
                self.assertEqual(recovered.match(mid)['analyses'], [])
                recovered.replay_control(mid, 'step')
                self.assertEqual(len(recovered.timeline(mid)['items']), 1)
                self.assertEqual(recovered.store.metrics()['duplicates_rejected'], 1)
            finally:
                recovered.close()


if __name__ == '__main__':
    unittest.main()
