"""Execute the native popup URL policy without rebuilding Tauri."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUSTC = Path.home() / '.cargo/bin/rustc.exe'


@unittest.skipUnless(os.name == 'nt' and RUSTC.is_file(), 'Existing Windows Rust toolchain required')
class DesktopPopupTests(unittest.TestCase):
    def test_native_popup_url_policy(self):
        scratch = ROOT / 'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='desktop-popup-', dir=scratch) as temporary:
            binary = Path(temporary) / 'external-target-tests.exe'
            compiled = subprocess.run([
                str(RUSTC), '--edition=2021', '--test',
                str(ROOT / 'client/desktop/src-tauri/src/external_target.rs'), '-o', str(binary),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn('3 passed; 0 failed', tested.stdout)


if __name__ == '__main__':
    unittest.main()
