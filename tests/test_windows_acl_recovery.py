"""Disposable behavioral checks for failed-installation reconciliation guards."""
from pathlib import Path
import importlib.util
import json
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acl_recovery_contract', ROOT / 'tests/installation/acl_recovery_contract.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AclRecoveryContractTests(unittest.TestCase):
    def setUp(self):
        scratch = m.LAB / 'tests'
        scratch.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix='acl-recovery-contract-', dir=scratch)
        self.addCleanup(temp.cleanup)
        self.lab = Path(temp.name)
        self.original = self.lab / 'old-operation'
        self.recovery = self.lab / 'new-operation'
        self.original.mkdir()
        self.recovery.mkdir()
        self.identity = 'core-next-' + 'a' * 32
        self.service = 'DragonhydraCoreNextcandidate' + self.identity[-12:]
        self.source = 'b' * 40
        self.profile_path = self.lab / 'profiles' / self.identity / 'installation-profile.json'
        self.profile_path.parent.mkdir(parents=True)
        self.profile = {'schema_version': 1, 'product': 'DRAGONHYDRA CORE NEXT', 'edition': 'CORE NEXT',
                        'environment_id': 'candidate', 'installation_id': self.identity,
                        'source_commit': self.source, 'lab_root': str(self.lab),
                        'install_root': str(self.profile_path.parent / 'application'),
                        'state_root': str(self.profile_path.parent / 'state'),
                        'browser_user_data': str(self.profile_path.parent / 'browser'),
                        'service_name': self.service, 'version': '0.5.0-dev.7', 'build_id': 'fixture-only',
                        'ports': {'api': 19990, 'web': 19991, 'database': 19992}}
        self.write(self.profile_path, self.profile)
        self.setup = self.lab / 'dist' / 'fixture.exe'
        self.setup.parent.mkdir()
        self.setup.write_bytes(b'fixture bytes; never executable')
        self.helper = self.lab / 'frozen-source' / 'CoreNextProfile.ps1'
        self.helper.parent.mkdir()
        self.helper.write_text('# fixture only\n')
        self.install_script = self.original / 'InstallFresh.ps1'
        self.install_script.write_text('# original fixture, never executed\n')
        self.plan = {'schema_version': 'core-next.dev7-windows-install-plan/1',
                     'installation_id': self.identity, 'service_name': self.service,
                     'source_commit': self.source, 'version': '0.5.0-dev.7', 'build_id': 'fixture-only',
                     'ports': self.profile['ports'], 'profile': self.bind(self.profile_path),
                     'setup': self.bind(self.setup), 'profile_helper': self.bind(self.helper)}
        self.receipt = {'schema_version': 'core-next.dev7-windows-phase/1', 'phase': 'InstallFresh',
                        'passed': False, 'stage': 'failed_reconciliation_required',
                        'failure_code': 'INSTALLER_FAILED_RECONCILE_NO_RETRY', 'automatic_retry': False,
                        'installer_exit_code': 1, 'installation_id': self.identity,
                        'source_commit': self.source, 'version': '0.5.0-dev.7',
                        'profile_sha256': m.digest(self.profile_path), 'setup_sha256': m.digest(self.setup)}
        self.operation = {'schema_version': 'core-next.acl-recovery-operation/1',
                          'operation_id': 'SYNTHETIC-ACL-RECOVERY-R1', 'operation_root': str(self.recovery),
                          'installation_id': self.identity, 'source_commit': self.source,
                          'service_name': self.service, 'service_account': r'NT AUTHORITY\LocalService',
                          'profile_sha256_before': m.digest(self.profile_path),
                          'automatic_retry': False, 'original_outcome': 'FAIL_PRESERVED'}
        self.operation_path = self.recovery / 'OPERATION.json'
        self.freeze()

    @staticmethod
    def write(path, doc):
        path.write_text(json.dumps(doc, indent=2), encoding='utf-8')

    @staticmethod
    def bind(path):
        return {'path': str(path), 'sha256': m.digest(path)}

    def freeze(self):
        self.write(self.original / 'PLAN.json', self.plan)
        self.receipt['plan_sha256'] = m.digest(self.original / 'PLAN.json')
        self.write(self.original / 'phase-InstallFresh.json', self.receipt)
        bindings = {'schema_version': 'core-next.dev7-install-draft-bindings/1',
                    'plan_sha256': self.receipt['plan_sha256'],
                    'install_fresh_sha256': m.digest(self.install_script), 'frozen_source_commit': self.source}
        self.write(self.original / 'BINDINGS.json', bindings)
        for name, filename in [('receipt', 'phase-InstallFresh.json'), ('plan', 'PLAN.json'),
                               ('bindings', 'BINDINGS.json'), ('install_script', 'InstallFresh.ps1')]:
            self.operation['original_' + name] = self.bind(self.original / filename)
        self.write(self.operation_path, self.operation)

    def validate(self):
        return m.validate_recovery(self.operation_path, m.digest(self.operation_path), lab_root=self.lab)

    def test_valid_failed_predecessor_is_only_evidence_validation(self):
        before = {p: m.digest(p) for p in (self.profile_path, *self.original.iterdir())}
        result = self.validate()
        self.assertTrue(result['validated'])
        self.assertFalse(result['release_accepted'])
        self.assertEqual(result['service_actions'], 0)
        self.assertEqual(result['original_outcome'], 'FAIL_PRESERVED')
        self.assertEqual(before, {p: m.digest(p) for p in before})

    def test_operation_hash_tamper_rejected(self):
        expected = m.digest(self.operation_path)
        self.operation_path.write_bytes(self.operation_path.read_bytes() + b' ')
        with self.assertRaisesRegex(m.RecoveryContractError, 'INPUT_CHANGED'):
            m.validate_recovery(self.operation_path, expected, lab_root=self.lab)

    def test_modified_profile_contents_rejected(self):
        self.profile_path.write_bytes(self.profile_path.read_bytes() + b' ')
        with self.assertRaisesRegex(m.RecoveryContractError, 'INPUT_CHANGED'):
            self.validate()

    def test_rebound_modified_profile_still_rejected_by_original_hash(self):
        self.profile['build_id'] = 'altered'
        self.write(self.profile_path, self.profile)
        self.plan['profile'] = self.bind(self.profile_path)
        self.plan['build_id'] = 'altered'
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'ACL_ONLY_PROFILE_HASH_CHANGED'):
            self.validate()

    def test_failed_receipt_cannot_be_claimed_successful(self):
        for field, value in [('passed', True), ('passed', 0), ('stage', 'passed'),
                             ('failure_code', 'OTHER_FAILURE'), ('installer_exit_code', 0)]:
            with self.subTest(field=field, value=value):
                old = self.receipt[field]
                self.receipt[field] = value
                self.freeze()
                with self.assertRaisesRegex(m.RecoveryContractError, 'FAILED_INSTALL_PREDECESSOR'):
                    self.validate()
                self.receipt[field] = old

    def test_failed_outcome_and_no_retry_are_required(self):
        for field, value in [('original_outcome', 'PASS'), ('automatic_retry', True)]:
            with self.subTest(field=field):
                old = self.operation[field]
                self.operation[field] = value
                self.freeze()
                with self.assertRaisesRegex(m.RecoveryContractError, 'FAILED_OUTCOME'):
                    self.validate()
                self.operation[field] = old

    def test_incorrect_service_identity_and_account_rejected(self):
        for field, value, code in [('service_name', 'DragonhydraWorkstation', 'SERVICE_IDENTITY'),
                                   ('service_account', r'NT AUTHORITY\SYSTEM', 'SERVICE_ACCOUNT')]:
            with self.subTest(field=field):
                old = self.operation[field]
                self.operation[field] = value
                self.freeze()
                with self.assertRaisesRegex(m.RecoveryContractError, code):
                    self.validate()
                self.operation[field] = old

    def test_invalid_installation_id_rejected(self):
        self.operation['installation_id'] = 'core-next-../other'
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'INSTALLATION_ID_REQUIRED'):
            self.validate()

    def test_wrong_predecessor_identity_rejected(self):
        self.receipt['installation_id'] = 'core-next-' + 'c' * 32
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'PREDECESSOR_IDENTITY'):
            self.validate()

    def test_original_receipt_bytes_are_hash_bound(self):
        path = self.original / 'phase-InstallFresh.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(m.RecoveryContractError, 'INPUT_CHANGED'):
            self.validate()

    def test_unowned_profile_and_installation_directories_rejected(self):
        old = self.profile_path
        self.profile_path = self.lab / 'other-profile.json'
        self.write(self.profile_path, self.profile)
        self.plan['profile'] = self.bind(self.profile_path)
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'UNAUTHORIZED_PROFILE_DIRECTORY'):
            self.validate()
        self.profile_path = old
        self.profile['state_root'] = str(self.lab / 'another-installation' / 'state')
        self.write(self.profile_path, self.profile)
        self.plan['profile'] = self.bind(self.profile_path)
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'UNAUTHORIZED_INSTALLATION_DIRECTORY'):
            self.validate()

    def test_original_operation_cannot_be_reused(self):
        self.operation['operation_root'] = str(self.original)
        self.operation_path = self.original / 'OPERATION.json'
        self.freeze()
        with self.assertRaisesRegex(m.RecoveryContractError, 'DISTINCT_RECOVERY_OPERATION'):
            self.validate()

    def test_changed_setup_and_helper_rejected(self):
        for path in (self.setup, self.helper):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.write_bytes(raw + b'changed')
                with self.assertRaisesRegex(m.RecoveryContractError, 'INPUT_CHANGED'):
                    self.validate()
                path.write_bytes(raw)

    def test_unbound_plan_script_and_source_rejected(self):
        bindings_path = self.original / 'BINDINGS.json'
        for field in ('plan_sha256', 'install_fresh_sha256', 'frozen_source_commit'):
            with self.subTest(field=field):
                self.freeze()
                bindings = m.load(bindings_path)
                bindings[field] = 'f' * len(bindings[field])
                self.write(bindings_path, bindings)
                self.operation['original_bindings'] = self.bind(bindings_path)
                self.write(self.operation_path, self.operation)
                with self.assertRaises(m.RecoveryContractError):
                    self.validate()

    def test_parent_traversal_is_not_normalized_into_success(self):
        path = str(self.recovery / '..' / 'new-operation' / 'OPERATION.json')
        with self.assertRaisesRegex(m.RecoveryContractError, 'ORDINARY_RECOVERY_PATH'):
            m.validate_recovery(path, m.digest(self.operation_path), lab_root=self.lab)

    def test_access_denied_profile_is_not_treated_as_missing_or_valid(self):
        original_lstat = Path.lstat
        def inaccessible(path, *args, **kwargs):
            if path == self.profile_path:
                raise PermissionError('fixture access denied')
            return original_lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', inaccessible):
            with self.assertRaises(m.RecoveryContractError) as caught:
                self.validate()
        self.assertIn('RECOVERY_PATH_ACCESS_DENIED', str(caught.exception))
        self.assertIn(str(self.profile_path), str(caught.exception))

    def test_junction_attribute_rejected_even_when_not_a_symbolic_link(self):
        original_lstat = Path.lstat
        def junction(path, *args, **kwargs):
            if path == self.profile_path.parent:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', junction):
            with self.assertRaisesRegex(m.RecoveryContractError, 'REPARSE_RECOVERY_PATH_REJECTED'):
                self.validate()


if __name__ == '__main__':
    unittest.main(verbosity=2)
