import json
from pathlib import Path
import unittest

from core_next.characterization import characterize


class LockedA9Characterization(unittest.TestCase):
    def test_fixed_clock_seed_and_full_algorithm_reports_match_locked_a9(self):
        expected = json.loads((Path(__file__).parent/'fixtures'/'a9-mathematics.json').read_text())
        actual = json.loads(json.dumps(characterize(), default=str))
        self.assertEqual(actual, expected['outputs'])
        self.assertEqual(expected['baseline_commit'], '2e6520d5b6a7874881e5de85dbb6ececaef11d8f')
