"""Offline ownership guards for the installed runtime acceptance helper."""
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


SPEC = importlib.util.spec_from_file_location('runtime_acceptance', Path(__file__).parents[1]/'scripts'/'verify_linux_a6_runtime.py')
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RuntimeOwnershipTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Linux virtual environment symlink regression')
    def test_server_command_preserves_virtual_environment_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root/'base-python'
            base.write_text('base interpreter placeholder')
            venv_python = root/'venv'/'bin'/'python'
            venv_python.parent.mkdir(parents=True)
            venv_python.symlink_to(base)
            args = SimpleNamespace(python=venv_python, launcher=None)
            self.assertEqual(runtime.server_command(args, root/'state')[0], str(venv_python))
            self.assertNotEqual(runtime.server_command(args, root/'state')[0], str(base))
            launcher = root/'venv'/'bin'/'dragonhydra-server'
            launcher.symlink_to(base)
            args.launcher = launcher
            self.assertEqual(runtime.server_command(args, root/'state')[0], str(launcher))

    def test_only_matching_owned_loopback_endpoint_is_accepted(self):
        self.assertEqual(runtime.checked_endpoint({'url': 'http://127.0.0.1:12345', 'pid': 42}, 42),
                         'http://127.0.0.1:12345')
        for endpoint in (
            {'url': 'http://127.0.0.1:12345', 'pid': 43},
            {'url': 'http://example.test:12345', 'pid': 42},
            {'url': 'http://secret@127.0.0.1:12345', 'pid': 42},
            {'url': 'https://127.0.0.1:12345', 'pid': 42},
            {'url': 'http://127.0.0.1:12345/unrelated', 'pid': 42},
            {'url': 'http://127.0.0.1:12345?token=secret', 'pid': 42},
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(AssertionError):
                runtime.checked_endpoint(endpoint, 42)


if __name__ == '__main__':
    unittest.main()
