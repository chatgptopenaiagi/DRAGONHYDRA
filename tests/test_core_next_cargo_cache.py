"""Dependency reuse contracts with synthetic files; never executes a cached app."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cargo_cache',ROOT/'scripts/core_next_cargo_cache.py')
cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)

class CargoCacheContracts(unittest.TestCase):
    def setUp(self):
        scratch=cache.LAB/'tests';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch,prefix='cargo-cache-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.target=self.base/'old-target';self.desktop=self.base/'desktop'
        for name in cache.INPUTS:
            path=self.desktop/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic '+name)
        self.binary=self.target/'x86_64-pc-windows-msvc/release/dragonhydra-desktop.exe'
        self.binary.parent.mkdir(parents=True);self.binary.write_bytes(b'fixture app, never executed')
        self.dep=self.target/'x86_64-pc-windows-msvc/release/deps/library.rlib';self.dep.parent.mkdir();self.dep.write_bytes(b'verified fixture dependency')
        own=self.dep.parent/'dragonhydra_desktop.pdb';own.write_bytes(b'own app output must not reuse')
        self.proof=self.base/'proof.json';self.proof.write_text(json.dumps(dict(compilation='PASS',source_sha='a'*40,source_content_sha256=cache.source_hash(self.desktop),files=[dict(path='DRAGONHYDRA-Client.exe',sha256=cache.digest(self.binary))])))
        self.manifest=self.base/'cache.json'
        self.version=patch.object(cache,'rust_version',lambda:'fixture rustc version');self.version.start();self.addCleanup(self.version.stop)
        cache.seal(self.target,self.desktop,self.proof,self.manifest)
    def test_copy_reuses_dependency_but_excludes_every_own_application_output(self):
        new=self.base/'new-target';result=cache.copy_cache(self.target,self.manifest,self.desktop,new)
        self.assertFalse(result['application_reused'])
        self.assertEqual((new/self.dep.relative_to(self.target)).read_bytes(),self.dep.read_bytes())
        self.assertFalse((new/self.binary.relative_to(self.target)).exists())
        self.assertFalse(any(cache.own_application(p.relative_to(new)) for p in new.rglob('*')))
    def test_modified_dependency_rejected_before_destination_creation(self):
        self.dep.write_bytes(b'tampered');new=self.base/'new-target'
        with self.assertRaises(ValueError):cache.copy_cache(self.target,self.manifest,self.desktop,new)
        self.assertFalse(new.exists())
    def test_changed_lock_rejected(self):
        lock=self.desktop/'src-tauri/Cargo.lock';lock.write_text('changed locked dependencies')
        with self.assertRaises(ValueError):cache.copy_cache(self.target,self.manifest,self.desktop,self.base/'new-target')
    def test_changed_rust_toolchain_rejected(self):
        with patch.object(cache,'rust_version',lambda:'different rustc'):
            with self.assertRaises(ValueError):cache.copy_cache(self.target,self.manifest,self.desktop,self.base/'new-target')
    def test_manifest_cannot_promote_application_or_escape_member(self):
        doc=json.loads(self.manifest.read_text())
        for name in ['../outside','x86_64-pc-windows-msvc/release/deps/dragonhydra_desktop.exe']:
            changed=dict(doc);changed['files']=[dict(doc['files'][0],path=name)];self.manifest.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):cache.copy_cache(self.target,self.manifest,self.desktop,self.base/'new-target')

if __name__=='__main__':unittest.main()
