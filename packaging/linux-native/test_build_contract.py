"""Negative native-builder provenance gates, without changing the frozen input."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('native_deb_builder', Path(__file__).with_name('build_deb.py'))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
FROZEN = ROOT/'build/linux/prep-20261031-r2/dragonhydra-linux-dev-9f3d6e5ab108'


class NativeBuilderContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime/linux-native/scratch', prefix='native-gate-')
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name)/'bundle'
        shutil.copytree(FROZEN, self.bundle)
        self.manifest = json.loads((self.bundle/'MANIFEST.json').read_text())

    def save(self):
        (self.bundle/'MANIFEST.json').write_text(json.dumps(self.manifest))

    def update(self, name):
        item = next(r for r in self.manifest['files'] if r['path']==name)
        path = self.bundle/name
        item.update(bytes=path.stat().st_size, sha256=builder.sha(path))

    def test_actual_frozen_input_has_matching_bundle_source_and_embedded_wheel_identity(self):
        _, source, wheel = builder.verify_bundle(self.bundle)
        self.assertEqual(source['source_content_sha256'], self.manifest['source_content_sha256'])
        self.assertTrue(wheel.is_file())

    def test_unlisted_missing_application_wheel_is_rejected(self):
        self.manifest['wheel'] = 'unlisted-py3-none-any.whl'
        self.save()
        with self.assertRaisesRegex(ValueError, 'verified bundle member'):
            builder.verify_bundle(self.bundle)

    def test_external_application_wheel_is_rejected_even_when_valid_zip_exists(self):
        shutil.copyfile(self.bundle/self.manifest['wheel'], Path(self.temp.name)/'external-py3-none-any.whl')
        self.manifest['wheel'] = '../external-py3-none-any.whl'
        self.save()
        with self.assertRaisesRegex(ValueError, 'verified bundle member'):
            builder.verify_bundle(self.bundle)

    def test_source_manifest_identity_must_match_its_exact_file_list(self):
        path = self.bundle/'SOURCE-MANIFEST.json'
        source = json.loads(path.read_text())
        source['source_content_sha256'] = 'f'*64
        path.write_text(json.dumps(source))
        self.update(path.name)
        self.save()
        with self.assertRaisesRegex(ValueError, 'source identity mismatch'):
            builder.verify_bundle(self.bundle)

    def test_wheel_with_updated_archive_hash_still_must_match_frozen_source_identity(self):
        path = self.bundle/self.manifest['wheel']
        with zipfile.ZipFile(path) as source:
            entries = {name: source.read(name) for name in source.namelist()}
        identity = json.loads(entries['dragonhydra/build_info.json'])
        identity['source_content_sha256'] = 'e'*64
        entries['dragonhydra/build_info.json'] = json.dumps(identity).encode()
        with zipfile.ZipFile(path, 'w') as target:
            for name, body in entries.items():
                target.writestr(name, body)
        self.update(path.name)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Embedded application wheel identity mismatch'):
            builder.verify_bundle(self.bundle)


if __name__=='__main__':
    unittest.main()
