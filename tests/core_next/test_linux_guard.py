"""Cross-platform binding checks; never starts a service or opens old state."""
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from dragonhydra.installation_profile import (WINDOWS_LAB_ROOT, load_binding,
    ordinary, posix_lab_root, selected_lab_root)


class LinuxRootParsing(unittest.TestCase):
    def test_posix_default_or_explicit_root_is_absolute_and_isolated(self):
        self.assertEqual(posix_lab_root('/var/lib/dragonhydra-core-next-lab'),
                         '/var/lib/dragonhydra-core-next-lab')
        self.assertEqual(posix_lab_root('/core-next-lab/owned'), '/core-next-lab/owned')
        for value in ('/', 'relative', '/owned/../old', '//host/share',
                      r'C:\xampp\DRAGONHYDRA', r'/owned\old', '/owned'+chr(10)+'control'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                posix_lab_root(value)

    @unittest.skipUnless(os.name == 'nt', 'Windows-specific fixed-root assertion')
    def test_windows_ignores_posix_override(self):
        with patch.dict(os.environ, {'DRAGONHYDRA_CORE_NEXT_LAB_ROOT': '/other/instance'}):
            self.assertEqual(selected_lab_root(), WINDOWS_LAB_ROOT)

    @unittest.skipUnless(os.name == 'posix', 'Executed by the isolated Linux container')
    def test_linux_override_and_profile_cannot_select_original_state_or_symlink(self):
        with tempfile.TemporaryDirectory(prefix='core-next-linux-guard-') as scratch:
            lab = Path(scratch)/'core-next-lab'; lab.mkdir()
            identifier = 'core-next-'+'d'*32
            root = lab/'profiles'/identifier; root.mkdir(parents=True)
            path = root/'installation-profile.json'
            profile = dict(schema_version=1, product='DRAGONHYDRA CORE NEXT', edition='CORE NEXT',
                installation_id=identifier, environment_id='candidate', lab_root=str(lab),
                install_root=str(root/'application'), state_root=str(root/'state'), browser_user_data=str(root/'browser'),
                ports=dict(api=18810, web=18811, database=18812), copy_credentials=False,
                provider_schedules='disabled', service_name='DragonhydraCoreNextcandidate'+'d'*12,
                source_commit='e'*40)
            path.write_text(json.dumps(profile))
            with patch.dict(os.environ, {'DRAGONHYDRA_CORE_NEXT_LAB_ROOT': str(lab)}):
                self.assertEqual(selected_lab_root(), lab)
                bound, state = load_binding(profile_path=path)
                self.assertEqual(state, root/'state'/'kernel')
                self.assertEqual(bound['installation_id'], identifier)
                with self.assertRaises(ValueError):
                    load_binding(state=Path('/var/lib/dragonhydra'), profile_path=path)
                destination = lab/'unrelated'; destination.mkdir()
                (root/'state').symlink_to(destination, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'REPARSE'):
                    load_binding(profile_path=path)

    def test_missing_profile_never_selects_a_fallback(self):
        with tempfile.TemporaryDirectory(prefix='core-next-missing-profile-') as scratch:
            with self.assertRaisesRegex(ValueError, 'PROFILE_REQUIRED'):
                load_binding(lab_root=Path(scratch))

    @unittest.skipUnless(os.name == 'posix', 'Actual shell guards run in isolated Linux')
    def test_new_wrapper_requires_profile_and_historical_entrypoints_fail_before_mutation(self):
        source = Path(__file__).resolve().parents[2]
        wrapper = source/'scripts/core_next/linux-server.sh'
        result = subprocess.run(['sh', str(wrapper)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 64)
        with tempfile.TemporaryDirectory(prefix='core-next-entry-guard-') as scratch:
            target = Path(scratch)/'must-not-be-created'
            for name in ('install.sh', 'run-server.sh'):
                result = subprocess.run(['sh', str(source/'packaging/linux'/name),
                    '--prefix', str(target), '--state', str(target/'state'), '--apply'],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(target.exists())
            result = subprocess.run([sys.executable, str(source/'packaging/linux/preflight.py'),
                '--prefix', str(target), '--state', str(target/'state'), '--apply'],
                capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 64)
            self.assertFalse(target.exists())
