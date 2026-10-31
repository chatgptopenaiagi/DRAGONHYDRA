"""Linux preparation integrity and default non-mutating target contracts."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('linux_bundle_builder_test', ROOT / 'scripts/build_linux_bundle.py')
preflight = module('linux_bundle_preflight_test', ROOT / 'packaging/linux/preflight.py')


class LinuxBundleTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='linux-bundle-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def fake_bundle(self):
        bundle = self.directory / 'bundle'
        bundle.mkdir()
        wheel = bundle / 'dragonhydra-0.4.0a1-py3-none-any.whl'
        wheel.write_bytes(b'fixture only; not an installed wheel')
        manifest = {'schema_version': 1, 'source_content_sha256': 'a' * 64, 'wheel': wheel.name,
                    'files': [{'path': wheel.name, 'bytes': wheel.stat().st_size,
                               'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}]}
        (bundle / 'MANIFEST.json').write_text(json.dumps(manifest))
        return bundle, wheel, manifest

    def test_integrity_checker_rejects_tampered_artifact(self):
        bundle, wheel, _ = self.fake_bundle()
        self.assertEqual(preflight.verify_bundle(bundle)['wheel'], wheel.name)
        wheel.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'BUNDLE_FILE_INTEGRITY'):
            preflight.verify_bundle(bundle)

    def test_manifest_cannot_escape_bundle_or_repeat_a_file(self):
        bundle, _, manifest = self.fake_bundle()
        for path in ('../outside', '/absolute', 'nested\\outside'):
            changed = json.loads(json.dumps(manifest))
            changed['files'][0]['path'] = path
            (bundle / 'MANIFEST.json').write_text(json.dumps(changed))
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'UNSAFE_BUNDLE_PATH'):
                preflight.verify_bundle(bundle)
        manifest['files'].append(manifest['files'][0])
        (bundle / 'MANIFEST.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'UNSAFE_BUNDLE_PATH'):
            preflight.verify_bundle(bundle)

    def test_default_preflight_creates_no_prefix_or_state_and_never_installs(self):
        bundle, _, _ = self.fake_bundle()
        prefix, state = self.directory / 'not-created-prefix', self.directory / 'not-created-state'
        output = io.StringIO()
        with patch('sys.argv', ['preflight', '--bundle', str(bundle), '--prefix', str(prefix), '--state', str(state)]), \
                patch.object(preflight, 'inspect_runtime', return_value={'ready': False}), \
                patch.object(preflight, 'install') as install, redirect_stdout(output):
            result = preflight.main()
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'requires_configuration')
        install.assert_not_called()
        self.assertFalse(prefix.exists())
        self.assertFalse(state.exists())

    def test_unsafe_install_targets_are_rejected(self):
        for target in ('relative', str(self.directory / 'percent%path'), str(self.directory / 'line\nbreak'), self.directory.anchor):
            with self.subTest(target=target), self.assertRaises(ValueError):
                preflight.safe_target(target)

    def test_current_source_scope_includes_features_and_excludes_live_state(self):
        files = builder.collect_inputs(ROOT)
        names = {item['path'] for item in files}
        self.assertIn('src/dragonhydra/local_ai.py', names)
        self.assertIn('src/dragonhydra/connectors/core.py', names)
        self.assertIn('packaging/linux/preflight.py', names)
        self.assertFalse(any(name.startswith(('runtime/', 'build/', 'dist/')) for name in names))
        self.assertFalse(any(Path(name).suffix in builder.FORBIDDEN for name in names))

    def test_malicious_wheel_member_is_rejected_without_extraction(self):
        wheel = self.directory / 'malformed-py3-none-any.whl'
        with ZipFile(wheel, 'w') as archive:
            archive.writestr('../escape.py', 'print("unexpected")')
        with self.assertRaisesRegex(ValueError, 'UNSAFE_WHEEL_MEMBER'):
            builder.inspect_wheel(wheel, 'a' * 64)
        self.assertFalse((self.directory.parent / 'escape.py').exists())

    def test_build_environment_uses_existing_interpreter_tools_without_carrying_provider_secrets(self):
        with patch.dict(os.environ, {'PATH': 'existing-path', 'PYTHONPATH': 'unrelated',
                                     'DRAGONHYDRA_TEST_KEY': 'synthetic-only'}):
            environment = builder.build_environment()
        self.assertEqual(environment['PATH'].split(os.pathsep)[0], str(Path(sys.executable).parent))
        self.assertNotIn('PYTHONPATH', environment)
        self.assertNotIn('DRAGONHYDRA_TEST_KEY', environment)


if __name__ == '__main__':
    unittest.main()
