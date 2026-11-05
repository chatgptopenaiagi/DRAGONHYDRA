"""Discoverable Windows NTFS/path regressions; no service or application launch."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
PS7 = Path(r'C:\Program Files\PowerShell\7\pwsh.exe')
PS5 = Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')


@unittest.skipUnless(os.name == 'nt', 'Windows NTFS and both installed PowerShell hosts required')
class ServiceAccessRegressions(unittest.TestCase):
    def run_fixture(self, host, script, required):
        self.assertTrue(host.is_file(), f'Registered PowerShell executable unavailable: {host}')
        fixture = ROOT / 'tests' / 'installation' / script
        self.assertTrue(fixture.is_file())
        scratch = LAB / 'tests'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='service-access-unittest-', dir=scratch) as temporary:
            arguments = [str(host), '-NoLogo', '-NoProfile', '-NonInteractive',
                         '-ExecutionPolicy', 'Bypass', '-File', str(fixture)]
            if script == 'check_profile_paths.ps1':
                arguments += ['-EvidenceRoot', temporary]
            completed = subprocess.run(arguments, cwd=ROOT, capture_output=True,
                                       text=True, encoding='utf-8-sig', errors='replace', timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stdout[-5000:] + completed.stderr[-5000:])
            result = json.loads(completed.stdout)
        self.assertIs(result.get('passed'), True)
        checks = result.get('checks', [])
        self.assertTrue(checks, 'Fixture must execute actual assertions')
        self.assertTrue(all(item.get('result') == 'PASS' for item in checks), checks)
        names = {item.get('check', item.get('name')) for item in checks}
        self.assertTrue(required <= names, f'Missing required regressions: {required - names}')
        if script == 'check_service_access.ps1':
            self.assertEqual(result.get('actual_service_calls'), 0)
            self.assertEqual(result.get('actual_native_calls'), 0)

    def service_fixture(self, host):
        self.run_fixture(host, 'check_service_access.ps1', {
            'INSTALLATION_ROOT_ACL', 'INSTALLATION_PROFILE_READ_ACCESS',
            'APPLICATION_EXECUTE_ACCESS', 'STATE_WRITE_ACCESS',
            'PROFILE_HASH_PRESERVATION', 'INCORRECT_SERVICE_IDENTITY',
            'INCORRECT_SERVICE_ACCOUNT', 'MODIFIED_PROFILE_REJECTED',
            'ADMINISTRATOR_IS_NOT_SERVICE_TOKEN', 'EXPLICIT_DENY_NOT_TREATED_AS_ACCESS',
            'ACCESS_PROVISIONED_BEFORE_SERVICE_START', 'NEW_SERVICE_RECOVERY_AFTER_READINESS',
            'ALL_REQUIRED_FILES_WRITE_DENIED', 'IMMUTABLE_TEST_PRESERVES_ALL_BYTES',
            'NEW_SERVICE_MANUAL_UNTIL_PROVISIONED', 'PROFILE_TIMESTAMP_NORMALIZATION',
        })

    def path_fixture(self, host):
        self.run_fixture(host, 'check_profile_paths.ps1', {
            'ORDINARY_PATH', 'PARENT_DIRECTORY_TRAVERSAL', 'DOTDOT_REJECTION',
            'OUTSIDE_BOUNDARY_REJECTION', 'REPARSE_POINT_REJECTION',
            'REPARSE_PARENT_REJECTION', 'ACCESS_DENIED_DIAGNOSTICS_CONTINUE',
            'UNKNOWN_PROVIDER_ERROR_FAILS_CLOSED', 'ACTUAL_NTFS_PROFILE_READ_DENIAL',
            'INVALID_INSTALLATION_ID', 'UNAUTHORIZED_INSTALLATION_DIRECTORY',
        })

    def test_service_acl_powershell7(self):
        self.service_fixture(PS7)

    def test_service_acl_windows_powershell51(self):
        self.service_fixture(PS5)

    def test_profile_paths_powershell7(self):
        self.path_fixture(PS7)

    def test_profile_paths_windows_powershell51(self):
        self.path_fixture(PS5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
