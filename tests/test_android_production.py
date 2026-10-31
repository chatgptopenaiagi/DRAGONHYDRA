"""Publisher-signing guard behavior without generating a key or production APK."""
import importlib.util
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('android_production_preflight', ROOT/'scripts/prepare_android_production.py')
production = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production)


class AndroidProductionTests(unittest.TestCase):
    def test_missing_identity_never_runs_tools_or_changes_files(self):
        runner = Mock(side_effect=AssertionError('No tool may run without an authorized configured identity'))
        before = {path.name for path in (ROOT/'build').iterdir()}
        result = production.preflight({}, run=runner)
        self.assertEqual(result['status'], 'requires_signing_configuration')
        self.assertFalse(result['files_changed'] or result['build_started'] or result['publisher_key_created'])
        self.assertEqual(before, {path.name for path in (ROOT/'build').iterdir()})
        runner.assert_not_called()

    def test_missing_expected_certificate_stops_before_any_tool_execution(self):
        environment = {production.PREFIX+name: 'fixture' for name in production.REQUIRED}
        del environment[production.PREFIX+'CERT_SHA256']
        runner = Mock()
        result = production.preflight(environment, run=runner)
        self.assertEqual(result['status'], 'requires_signing_configuration')
        self.assertEqual(result['missing_environment'], [production.PREFIX+'CERT_SHA256'])
        runner.assert_not_called()

    def test_known_debug_certificate_is_never_accepted(self):
        with self.assertRaises(production.SigningError) as error:
            production.fingerprint(production.DEBUG_CERTIFICATE)
        self.assertEqual(str(error.exception), 'debug_identity_rejected')
        with self.assertRaises(production.SigningError):
            production.validate_identity('ab'*32, 'ab'*32, 'CN=Android Debug,O=Android,C=US')

    def test_mismatch_and_certificate_only_entry_are_rejected(self):
        with self.assertRaises(production.SigningError) as error:
            production.validate_identity('ab'*32, 'cd'*32)
        self.assertEqual(str(error.exception), 'certificate_fingerprint_mismatch')
        with self.assertRaises(production.SigningError) as error:
            production.validate_identity('ab'*32, 'ab'*32, entry_type='trustedCertEntry')
        self.assertEqual(str(error.exception), 'publisher_private_key_entry_required')

    def test_certificate_fingerprint_shape_and_colons(self):
        self.assertEqual(production.fingerprint(':'.join(['AB']*32)), 'ab'*32)
        for value in ('', 'a'*63, 'a'*65, 'z'*64):
            with self.assertRaises(production.SigningError):
                production.fingerprint(value)

    def test_filename_and_alias_labels_do_not_replace_certificate_identity(self):
        # These bytes are not a key or certificate. The tool boundary is mocked;
        # this test verifies label handling and password argument hygiene only.
        with tempfile.TemporaryDirectory(dir=ROOT/'build/android-signing', prefix='non-key-fixture-') as directory:
            non_key = Path(directory)/'debug.keystore'
            non_key.write_text('This is a non-key test fixture.', encoding='utf-8')
            fixture_bytes = b'non-certificate fixture bytes'
            pem = b'-----BEGIN CERTIFICATE-----\n'+base64.b64encode(fixture_bytes)+b'\n-----END CERTIFICATE-----\n'
            environment = {production.PREFIX+name: 'fixture-password-not-a-real-secret' for name in production.REQUIRED}
            environment[production.PREFIX+'KEYSTORE'] = str(non_key.resolve())
            environment[production.PREFIX+'KEY_ALIAS'] = 'androiddebugkey'
            environment[production.PREFIX+'CERT_SHA256'] = hashlib.sha256(fixture_bytes).hexdigest()
            runner = Mock(side_effect=[
                SimpleNamespace(returncode=0, stdout=b'Entry type: PrivateKeyEntry\nOwner: CN=Fixture Publisher,O=Fixture\n'),
                SimpleNamespace(returncode=0, stdout=pem),
            ])
            with patch.object(production, 'KEYTOOL', non_key):
                result = production.preflight(environment, run=runner)
            self.assertEqual(result['status'], 'certificate_configuration_verified')
            self.assertFalse(result['private_key_password_verified'])
            self.assertEqual(runner.call_count, 2)
            for invoked in runner.call_args_list:
                self.assertIn('-storepass:env', invoked.args[0])
                self.assertNotIn(environment[production.PREFIX+'STORE_PASSWORD'], invoked.args[0])

    def test_actual_no_key_cli_has_clear_blocker_and_no_created_work_directory(self):
        environment = {key:value for key,value in os.environ.items() if not key.startswith(production.PREFIX)}
        result = subprocess.run([sys.executable, '-B', ROOT/'scripts/prepare_android_production.py'],
                                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        response = json.loads(result.stdout)
        self.assertEqual(response['status'], 'requires_signing_configuration')
        self.assertFalse(response['files_changed'])


if __name__ == '__main__':
    unittest.main()
