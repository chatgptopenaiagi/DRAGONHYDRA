"""Prove native package upgrades do not sort by arbitrary source hash."""
import platform
from pathlib import Path
import runpy
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
version = runpy.run_path(str(ROOT/'packaging/linux-native/build_deb.py'))['debian_version']
OLD = '9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4'


class DebianVersions(unittest.TestCase):
    def greater(self, newer, older):
        result = subprocess.run(['dpkg', '--compare-versions', newer, 'gt', older], capture_output=True)
        self.assertEqual(result.returncode, 0, (newer, older, result.stderr))

    def test_legacy_candidate_names_unchanged(self):
        self.assertEqual(version(OLD, 6), '0.4.0~alpha.1+dev20261031.9f3d6e5ab108-6')

    def test_new_source_hash_must_not_make_upgrade_a_downgrade(self):
        previous = version(OLD, 6)
        self.assertNotEqual(subprocess.run(['dpkg', '--compare-versions',
            '0.4.0~alpha.1+dev20261031.000000000000-7', 'gt', previous]).returncode, 0)
        for digest in ('0'*64, 'f'*64, OLD):
            with self.subTest(digest=digest):
                self.greater(version(digest, 7), previous)

    def test_sequence_wins_over_opposite_hash_order(self):
        for before, after in ((7, 8), (9, 10), (98, 99), (998, 999)):
            with self.subTest(before=before, after=after):
                self.greater(version('0'*64, after), version('f'*64, before))

    def test_invalid_or_reused_legacy_inputs_fail_closed(self):
        for digest, sequence in (('x'*64, 7), ('0'*63, 7), ('0'*64, 6), (OLD, True), (OLD, 0), (OLD, 1000)):
            with self.subTest(digest=digest, sequence=sequence):
                with self.assertRaises(ValueError):
                    version(digest, sequence)


if __name__ == '__main__':
    if platform.system() != 'Linux':
        raise SystemExit('Run with the native Linux dpkg version comparator.')
    unittest.main(verbosity=2)
