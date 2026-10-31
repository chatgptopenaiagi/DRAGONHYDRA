"""Isolated guards for the prepared R7-to-R8 upgrader; never call its main."""
from contextlib import closing
from copy import deepcopy
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('a5_upgrade_guard_target', Path(__file__).with_name('linux_a5_upgrade.py'))
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


def schema(*, retry=True):
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('CREATE TABLE product_jobs(id TEXT PRIMARY KEY,status TEXT,attempts INTEGER,cancel_requested INTEGER,deadline REAL,lease_until REAL,heartbeat REAL'
                   + (',next_attempt REAL NOT NULL DEFAULT 0' if retry else '') + ')')
        return target.database_schema(db)


class Guards(unittest.TestCase):
    def test_exact_r7_to_r8_contract(self):
        self.assertEqual(target.CURRENT_HASH, '02229cd57f01c36391df2a966f11f9275feed9f8aacdc8dc5640766439882605')
        self.assertEqual(target.ARTIFACT_HASH, 'd8b741ee36921a536a4624e4c351f8f790c89b75e9bd2bea6127a72b865dd675')
        self.assertEqual(target.CONTRACT['target_payload_files'], 1370)
        self.assertEqual(target.CONTRACT['target_bytes'], 2939100)
        self.assertFalse(target.CONTRACT['application_origin_embedded_in_software'])
        self.assertEqual(target.URL, 'http://127.0.0.1:55971')

    def test_preflight_rejects_all_mutating_commands_without_subprocess(self):
        artifact = str(ROOT/'dist/linux/native-kernel-20261031/r8'/('dragonhydra-api_'+target.VERSION+'_amd64.deb'))
        commands = (['dpkg', '--install', artifact], ['systemctl', 'start', target.UNIT],
                    ['systemctl', 'reset-failed', target.UNIT], ['/usr/bin/python3', '-B', str(ROOT/'tests/installation/linux_systemd_package.py')])
        with patch.object(subprocess, 'run', side_effect=AssertionError('No subprocess is allowed in these guard tests')):
            for command in commands:
                with self.subTest(command=command[0]):
                    with self.assertRaises(RuntimeError):
                        target.command_guard(command, False)

    def test_readonly_commands_are_allowed_without_execution(self):
        for command in (['systemctl', 'show', target.UNIT], ['dpkg-query', '-W', 'dragonhydra-api'],
                        ['dpkg', '--compare-versions', target.VERSION, 'gt', target.CURRENT_VERSION],
                        ['sh', '-n', 'a-owned-script'], ['journalctl', '-u', target.UNIT]):
            target.command_guard(command, False)

    def test_apply_is_scoped_to_exact_archive_and_unit(self):
        artifact = str(ROOT/'dist/linux/native-kernel-20261031/r8'/('dragonhydra-api_'+target.VERSION+'_amd64.deb'))
        target.command_guard(['dpkg', '--install', artifact], True)
        target.command_guard(['systemctl', 'start', target.UNIT], True)
        for command in (['dpkg', '--install', '/other.deb'], ['systemctl', 'start', 'unrelated.service'],
                        ['systemctl', 'start', 'unrelated.service', target.UNIT], ['systemctl', 'stop', target.MODEL_UNIT],
                        ['apt', 'install', 'anything'], ['sh', '-c', 'anything']):
            with self.subTest(command=command[0]):
                with self.assertRaises(RuntimeError):
                    target.command_guard(command, True)

    def test_unchanged_job_schema_accepted(self):
        before = schema()
        result = target.validate_schema_change(before, deepcopy(before))
        self.assertTrue(result['job_claim_columns_present'])
        self.assertEqual(result['allowed_appended_columns'], [])
        self.assertFalse(result['context_tables_added'])

    def test_only_known_retry_column_is_additive(self):
        before = schema(retry=False)
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute(next(item[3] for item in before['objects'] if item[:2] == ['table', 'product_jobs']))
            db.execute('ALTER TABLE product_jobs ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0')
            after = target.database_schema(db)
        self.assertEqual(target.validate_schema_change(before, after)['allowed_appended_columns'], ['product_jobs.next_attempt'])

    def test_existing_column_type_or_order_drift_is_rejected(self):
        before = schema()
        for alter in ('type', 'order', 'drop'):
            after = deepcopy(before)
            if alter == 'type':
                after['columns']['product_jobs'][2][2] = 'TEXT'
            elif alter == 'order':
                after['columns']['product_jobs'][1:3] = reversed(after['columns']['product_jobs'][1:3])
            else:
                after['columns']['product_jobs'].pop(2)
            with self.subTest(alter=alter):
                with self.assertRaises(RuntimeError):
                    target.validate_schema_change(before, after)

    def test_silent_context_table_or_trigger_ddl_is_rejected(self):
        before = schema()
        after = deepcopy(before)
        after['columns']['cognitive_records'] = []
        with self.assertRaises(RuntimeError):
            target.validate_schema_change(before, after)
        after = deepcopy(before)
        after['objects'].append(['trigger', 'unexpected', 'product_jobs', 'anything'])
        with self.assertRaises(RuntimeError):
            target.validate_schema_change(before, after)

    def test_unreviewed_column_or_retry_default_is_rejected(self):
        before = schema(retry=False)
        for extra in ([7, 'next_attempt', 'REAL', 1, '1', 0], [7, 'unexpected', 'TEXT', 0, None, 0]):
            after = deepcopy(before)
            after['columns']['product_jobs'].append(extra)
            with self.subTest(column=extra[1]):
                with self.assertRaises(RuntimeError):
                    target.validate_schema_change(before, after)

    def test_empty_optional_ai_and_inactive_not_found_are_accepted(self):
        config = {'configured': False, 'endpoint': '', 'credential_source': 'none'}
        target.validate_ai_state({'DropInPaths': ''}, {'ActiveState': 'inactive', 'LoadState': 'not-found', 'FragmentPath': ''}, config)
        target.validate_ai_state({'DropInPaths': ''}, {'ActiveState': 'inactive', 'LoadState': 'loaded', 'FragmentPath': str(target.MODEL_UNIT_PATH)}, config,
                                 {'owner': target.AI_OWNER, 'enabled': False})

    def test_only_explicit_not_found_probe_exit_is_accepted(self):
        config = {'configured': False, 'endpoint': '', 'credential_source': 'none'}
        absent = {'ActiveState': 'inactive', 'LoadState': 'not-found', 'FragmentPath': ''}
        target.validate_ai_state({'DropInPaths': ''}, absent, config, probe_exit=4)
        for code in (1, 9):
            with self.assertRaises(RuntimeError):
                target.validate_ai_state({'DropInPaths': ''}, absent, config, probe_exit=code)
        with self.assertRaises(RuntimeError):
            target.validate_ai_state({'DropInPaths': ''}, {**absent, 'LoadState': 'error'}, config, probe_exit=4)

    def test_active_and_failed_models_are_rejected_without_stopping_them(self):
        for state in ('active', 'activating', 'deactivating', 'failed'):
            with self.subTest(state=state):
                with self.assertRaises(RuntimeError):
                    target.validate_ai_state({'DropInPaths': ''}, {'ActiveState': state, 'LoadState': 'loaded', 'FragmentPath': ''},
                                             {'configured': False, 'endpoint': '', 'credential_source': 'none'})

    def test_dropins_or_existing_model_configuration_are_rejected(self):
        model = {'ActiveState': 'inactive', 'LoadState': 'not-found', 'FragmentPath': ''}
        empty = {'configured': False, 'endpoint': '', 'credential_source': 'none'}
        for props, config in (({'DropInPaths': '/run/temporary.conf'}, empty), ({'DropInPaths': ''}, {**empty, 'configured': True}),
                              ({'DropInPaths': ''}, {**empty, 'endpoint': 'http://127.0.0.1:12345'}),
                              ({'DropInPaths': ''}, {**empty, 'credential_source': 'environment'})):
            with self.assertRaises(RuntimeError):
                target.validate_ai_state(props, model, config)

    def test_foreign_inactive_model_unit_and_enabled_marker_are_rejected(self):
        config = {'configured': False, 'endpoint': '', 'credential_source': 'none'}
        for fragment, marker in (('/usr/lib/systemd/system/foreign.service', None), (str(target.MODEL_UNIT_PATH), None),
                                 (str(target.MODEL_UNIT_PATH), {'owner': target.AI_OWNER, 'enabled': True})):
            with self.assertRaises(RuntimeError):
                target.validate_ai_state({'DropInPaths': ''}, {'ActiveState': 'inactive', 'LoadState': 'loaded', 'FragmentPath': fragment}, config, marker)

    def test_successful_source_helpers_remain_unchanged(self):
        self.assertEqual(target.digest(ROOT/'tests/installation/linux_frozen_upgrade.py'), target.REUSED_UPGRADE_SHA256)
        self.assertEqual(target.digest(ROOT/'tests/installation/linux_systemd_package.py'), target.RUNTIME_HARNESS_SHA256)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    evidence = args.work.resolve()
    boundary = ROOT/'build/linux/native-kernel-20261031/system-install-8/preparation'
    if not evidence.is_relative_to(boundary) or evidence == boundary or evidence.exists():
        raise SystemExit('Preserve prior guard regression evidence; choose a fresh suffix deliberately.')
    evidence.mkdir(parents=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Guards)
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    output = stream.getvalue()
    (evidence/'unittest.log').write_text(output)
    report = {'passed': result.wasSuccessful(), 'unique_cases': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skips': len(result.skipped), 'seconds': round(time.monotonic()-started, 3),
              'scope': 'Isolated in-memory schema and pure command/optional-state guards; no upgrade, service, network or operational database execution.',
              'harness_sha256': hashlib.sha256(Path(__file__).with_name('linux_a5_upgrade.py').read_bytes()).hexdigest(),
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (evidence/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(output)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
