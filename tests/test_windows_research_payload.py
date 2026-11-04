"""Frozen SQL support must carry the reviewed schema and verified native input.

These tests exercise the actual source selection/spec/payload gates. They never
build an executable, connect to SQL Server, or modify an installed profile.
"""
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('windows_research_builder', ROOT/'scripts/build_connector_server.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ResearchPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self):
        for relative in builder.RESEARCH_INPUTS:
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'SYNTHETIC schema' if path.suffix == '.sql' else b'# SYNTHETIC source\n')
        return self.root

    def distribution(self, version='5.3.0', *, hashed=True, names=('pyodbc.cp314-win_amd64.pyd',)):
        from importlib.metadata import PackagePath
        files = []
        for name in names:
            entry = PackagePath(name)
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'SYNTHETIC native extension ' + name.encode())
            sha = hashlib.sha256(path.read_bytes()).digest()
            entry.hash = SimpleNamespace(mode='sha256', value=base64.urlsafe_b64encode(sha).decode().rstrip('=')) if hashed else None
            entry.size = path.stat().st_size
            files.append(entry)
        lock = self.root/builder.SQL_DRIVER_LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        self.wheel = self.root/'pyodbc-5.3.0-cp314-cp314-win_amd64.whl'
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            for entry in files:
                archive.write(self.root/entry, entry.as_posix())
        lock.write_text('pyodbc==5.3.0 --hash=sha256:'+builder.digest(self.wheel)+'\n')
        return SimpleNamespace(version=version, files=files, locate_file=lambda entry:self.root/entry)

    def test_reviewed_sql_schema_and_every_adapter_are_manifest_inputs(self):
        selected = builder.product_inputs(self.source())
        self.assertEqual(set(selected), {self.root/path for path in builder.RESEARCH_INPUTS})

    def test_missing_schema_is_rejected_before_snapshot(self):
        self.source()
        (self.root/builder.SQL_SCHEMA).unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing a research'):
            builder.product_inputs(self.root)

    def test_missing_adapter_is_rejected(self):
        self.source()
        (self.root/'src/dragonhydra/research_storage/service.py').unlink()
        with self.assertRaises(RuntimeError):
            builder.product_inputs(self.root)

    def test_arbitrary_sql_resource_is_not_silently_packaged(self):
        self.source()
        (self.root/'src/dragonhydra/research_storage/private.sql').write_text('SYNTHETIC private state')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected product source'):
            builder.product_inputs(self.root)

    def test_generated_metadata_is_excluded_but_other_private_json_rejected(self):
        self.source()
        generated = self.root/'src/dragonhydra/build_info.json'
        generated.write_text('{}')
        self.assertNotIn(generated, builder.product_inputs(self.root))
        generated.rename(generated.with_name('workstation.json'))
        with self.assertRaises(RuntimeError):
            builder.product_inputs(self.root)

    def test_spec_explicitly_loads_driver_hook_and_preserves_schema_relative_path(self):
        hooks = ModuleType('PyInstaller.utils.hooks')
        hooks.collect_submodules = lambda name:['uvicorn.synthetic']
        hooks.collect_data_files = lambda name:[]
        observed = {}
        def analysis(*args, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=kwargs['datas'])
        fake = {'PyInstaller':ModuleType('PyInstaller'), 'PyInstaller.utils':ModuleType('PyInstaller.utils'),
                'PyInstaller.utils.hooks':hooks}
        globals_ = dict(SPECPATH=str(ROOT/'packaging/windows'), Analysis=analysis,
                        PYZ=lambda *a, **k:None, EXE=lambda *a, **k:None, COLLECT=lambda *a, **k:None)
        with patch.dict(sys.modules, fake), patch.dict(os.environ, {}, clear=True):
            runpy.run_path(str(ROOT/'packaging/windows/product-server.spec'), init_globals=globals_)
        self.assertIn('pyodbc', observed['hiddenimports'])
        self.assertIn((str(ROOT/builder.SQL_SCHEMA), 'dragonhydra/research_storage'), observed['datas'])

    def test_hash_verified_pinned_driver_is_accepted_without_connecting(self):
        dist = self.distribution()
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist):
            result = builder.research_driver(self.root, self.wheel)
        self.assertEqual(result['version'], '5.3.0')
        self.assertEqual(len(result['binaries']), 1)
        self.assertIn('neither is bundled', result['host_prerequisite'])

    def test_wrong_driver_version_is_rejected(self):
        dist = self.distribution(version='0.0.0')
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def test_missing_native_connector_is_rejected(self):
        dist = self.distribution(names=())
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def test_wrong_python_or_architecture_extension_is_rejected(self):
        dist = self.distribution(names=('pyodbc.cp313-win_amd64.pyd',))
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def test_unhashed_installed_native_binary_is_rejected(self):
        dist = self.distribution(hashed=False)
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def test_tampered_installed_native_binary_is_rejected(self):
        dist = self.distribution()
        (self.root/'pyodbc.cp314-win_amd64.pyd').write_bytes(b'SYNTHETIC changed')
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def test_changed_cached_wheel_fails_before_installed_driver_is_used(self):
        dist = self.distribution()
        self.wheel.write_bytes(self.wheel.read_bytes()+b'SYNTHETIC changed')
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaisesRegex(RuntimeError, 'dependency lock'):
            builder.research_driver(self.root, self.wheel)

    def test_installed_native_record_rewritten_alongside_binary_still_fails_locked_wheel(self):
        dist = self.distribution()
        path = self.root/'pyodbc.cp314-win_amd64.pyd'
        path.write_bytes(b'SYNTHETIC changed native')
        dist.files[0].hash.value = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip('=')
        dist.files[0].size = path.stat().st_size
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist), self.assertRaises(RuntimeError):
            builder.research_driver(self.root, self.wheel)

    def payload(self):
        self.source()
        dist = self.distribution(names=('pyodbc.cp314-win_amd64.pyd', 'vendor/dependency.dll'))
        with patch.object(builder.importlib.metadata, 'distribution', return_value=dist):
            driver = builder.research_driver(self.root, self.wheel)
        payload = self.root/'payload'
        schema = payload/'_internal/dragonhydra/research_storage/schema_sqlserver.sql'
        schema.parent.mkdir(parents=True)
        schema.write_bytes((self.root/builder.SQL_SCHEMA).read_bytes())
        for entry in driver['binaries']:
            path = payload/'_internal'/entry['name']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(Path(entry['path']).read_bytes())
        return payload, driver, schema

    def test_complete_payload_including_vendor_dependency_matches(self):
        payload, driver, _ = self.payload()
        builder.verify_research_payload(payload, self.root, driver)

    def test_absent_or_wrong_sql_schema_fails_payload_gate(self):
        payload, driver, schema = self.payload()
        schema.write_bytes(b'SYNTHETIC wrong schema')
        with self.assertRaisesRegex(RuntimeError, 'SQL schema'):
            builder.verify_research_payload(payload, self.root, driver)
        schema.unlink()
        with self.assertRaises(RuntimeError):
            builder.verify_research_payload(payload, self.root, driver)

    def test_missing_or_modified_connector_fails_payload_gate(self):
        payload, driver, _ = self.payload()
        native = payload/'_internal/pyodbc.cp314-win_amd64.pyd'
        native.write_bytes(b'SYNTHETIC wrong extension')
        with self.assertRaisesRegex(RuntimeError, 'connector binary'):
            builder.verify_research_payload(payload, self.root, driver)
        native.unlink()
        with self.assertRaises(RuntimeError):
            builder.verify_research_payload(payload, self.root, driver)

    def test_vendor_dependency_cannot_be_missing_or_basename_substituted(self):
        payload, driver, _ = self.payload()
        vendor = payload/'_internal/vendor/dependency.dll'
        vendor.rename(payload/'_internal/dependency.dll')
        with self.assertRaises(RuntimeError):
            builder.verify_research_payload(payload, self.root, driver)

    def guidance(self):
        for source, _ in builder.PUBLIC_RESEARCH_INPUTS:
            path = self.root/source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC public example/lock/instructions: '+source.as_posix())
        return self.root/'standalone'

    def test_standalone_public_config_lock_and_guide_are_exact_source_bytes(self):
        payload = self.guidance()
        builder.copy_research_guidance(payload, self.root)
        self.assertEqual({target.as_posix() for _, target in builder.PUBLIC_RESEARCH_INPUTS},
                         {'config/research-storage.example.json', 'config/runtime/sqlserver-python314-windows.lock.txt',
                          'docs/MICROSOFT-SQLSERVER-INTEGRATION.md'})
        for source, target in builder.PUBLIC_RESEARCH_INPUTS:
            self.assertEqual((payload/target).read_bytes(), (self.root/source).read_bytes())
        self.assertEqual(sum(p.is_file() for p in payload.rglob('*')), 3)
        self.assertFalse((payload/'workstation.json').exists())

    def test_missing_public_guide_does_not_produce_success(self):
        payload = self.guidance()
        (self.root/'docs/integrations/MICROSOFT-SQLSERVER-INTEGRATION.md').unlink()
        with self.assertRaises(FileNotFoundError):
            builder.copy_research_guidance(payload, self.root)

    def test_changed_copied_public_guidance_is_rejected_before_manifest(self):
        payload = self.guidance()
        original_copy = builder.shutil.copyfile
        def corrupt(source, target):
            original_copy(source, target)
            Path(target).write_bytes(Path(target).read_bytes()+b'SYNTHETIC drift')
        with patch.object(builder.shutil, 'copyfile', side_effect=corrupt), self.assertRaisesRegex(RuntimeError, 'changed while copying'):
            builder.copy_research_guidance(payload, self.root)


if __name__ == '__main__':
    unittest.main()
