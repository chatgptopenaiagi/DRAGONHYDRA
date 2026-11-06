"""Curated-package tests use fictional in-memory bytes and disposable directories.

No final package build, application server, dependency install or network call.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from dragonhydra.future_relevance import server

SOURCE = Path(__file__).absolute().parents[1]
spec = importlib.util.spec_from_file_location('genesis61_fixture_builder', SOURCE/'scripts'/'build_genesis61.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
SHA = '1234567890abcdef1234567890abcdef12345678'


class Genesis61PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='genesis61-package-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.entries = {name:b'# fictional fixture bytes\n' for name in builder.REQUIRED}
        self.entries['src/dragonhydra/future_relevance/__init__.py'] = ('VERSION = '+repr(builder.VERSION)+'\n').encode()
        self.entries['tests/test_realtime_fixture.py'] = b'# fictional package fixture, never executed\n'
        self.entries['config/runtime/server-python314.lock.txt'] = b'# public dependency specifications only\n'
        self.raw, self.build = builder.package_bytes(SHA,self.entries,1700000000)
        with ZipFile(io.BytesIO(self.raw)) as archive: archive.extractall(self.base)
        self.source = self.base/'GENESIS-6.1-FUTURE-RELEVANCE'/'source'
        guard = patch.object(server,'SOURCE',self.source)
        guard.start(); self.addCleanup(guard.stop)

    def identity(self):
        with patch.object(server.subprocess,'run',side_effect=AssertionError('PACKAGE_MUST_NOT_QUERY_GIT')):
            return server.source_identity()

    def change_manifest(self, action):
        path = self.source/builder.MANIFEST
        value = json.loads(path.read_bytes())
        action(value)
        path.write_bytes(builder.encoded(value))
        build = json.loads((self.source/builder.BUILD).read_bytes())
        build['payload_manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.source/builder.BUILD).write_bytes(builder.encoded(build))

    def test_deterministic_zip_prefix_and_source_bound_manifest(self):
        again, info = builder.package_bytes(SHA,dict(reversed(list(self.entries.items()))),1700000000)
        self.assertEqual(self.raw,again)
        self.assertEqual(self.build,info)
        with ZipFile(io.BytesIO(self.raw)) as archive:
            self.assertEqual(archive.namelist(),sorted(archive.namelist()))
            self.assertTrue(all(n.startswith(builder.PREFIX) for n in archive.namelist()))
            self.assertTrue(all(i.date_time==(1980,1,1,0,0,0) for i in archive.infolist()))
        result = self.identity()
        self.assertEqual(result['source_sha'],SHA)
        self.assertEqual(result['component_version'],'0.2.0-virtual-experimental')
        self.assertIs(result['payload_verified'],True)
        self.assertIs(result['source_dirty'],False)
        self.assertEqual(result['verification_scope'],'LOCAL_PAYLOAD_SHA256_MANIFEST_AT_STARTUP')

    def test_finite_curated_policy_excludes_data_state_fixtures_and_credentials(self):
        self.assertIs(builder.curated,server.package_member_allowed)
        denied = ['src/dragonhydra/resources/data/raw/real.csv','src/dragonhydra/resources/examples/sample.json',
                  'tests/fixtures/real.json','tests/test_original_forecasts.py','examples/real.json',
                  'runtime/core.sqlite3','credentials.json','.env','state/session.json',
                  'src/dragonhydra/__pycache__/server.pyc','../outside.py','/absolute.py',
                  'src//dragonhydra/api.py','src/dragonhydra/../../escape.py','C:/private.py',
                  'src/dragonhydra/resources/web/secret.json','src/dragonhydra/resources/web/nested/app.js']
        allowed = list(self.entries)+['client/desktop/web/realtime.js','docs/realtime/MODELS.md',
            'scripts/accept_genesis6.py','scripts/browser_genesis6.py','scripts/accept_genesis61.py',
            'scripts/browser_genesis61.py','scripts/benchmark_genesis61.py','scripts/Verify-Genesis61.ps1',
            'tests/test_future_api.py','tests/test_genesis61_package.py','docs/future-relevance/DASHBOARD.md']
        for name in denied:
            with self.subTest(name=name):
                self.assertFalse(builder.curated(name))
                self.assertFalse(server.package_member_allowed(name))
        for name in allowed:
            with self.subTest(name=name):
                self.assertTrue(builder.curated(name))
                self.assertTrue(server.package_member_allowed(name))
        contaminated = {**self.entries,'src/dragonhydra/resources/data/raw/real.csv':b'never included'}
        with self.assertRaisesRegex(ValueError,'CURATED_REQUIRED_FILES_MISMATCH'):
            builder.package_bytes(SHA,contaminated,1700000000)

    def test_modified_missing_or_extra_payload_never_verified(self):
        target = self.source/'src/dragonhydra/future_relevance/service.py'
        original = target.read_bytes()
        target.write_bytes(original.replace(b'fictional',b'FICTIONAL'))
        with self.assertRaisesRegex(RuntimeError,'FILE_HASH_MISMATCH'): self.identity()
        target.unlink()
        with self.assertRaisesRegex(RuntimeError,'FILE_MISSING_OR_OVERSIZE'): self.identity()
        target.write_bytes(original)
        extra = self.source/'extra.txt'
        extra.write_bytes(b'not part of the curated source')
        with self.assertRaisesRegex(RuntimeError,'INVENTORY_MISMATCH'): self.identity()

    def test_changed_manifest_build_identity_and_version_fail_closed(self):
        manifest_path = self.source/builder.MANIFEST
        original_manifest = manifest_path.read_bytes()
        manifest_path.write_bytes(original_manifest+b' ')
        with self.assertRaisesRegex(RuntimeError,'MANIFEST_HASH_MISMATCH'): self.identity()
        manifest_path.write_bytes(original_manifest)
        build_path = self.source/builder.BUILD
        original_build = build_path.read_bytes()
        for field,value,code in [('source_sha','f'*40,'SOURCE_MISMATCH'),
                                 ('component_version','0.1.1','VERSION_MISMATCH'),
                                 ('synthetic_only',False,'SCOPE_MISMATCH'),
                                 ('dependencies_included',True,'SCOPE_MISMATCH')]:
            with self.subTest(field=field):
                build=json.loads(original_build);build[field]=value
                build_path.write_bytes(builder.encoded(build))
                with self.assertRaisesRegex(RuntimeError,code): self.identity()
        build_path.write_bytes(original_build)
        self.assertTrue(self.identity()['payload_verified'])

    def test_manifest_traversal_collision_forbidden_files_and_blob_hash_rejected(self):
        original_manifest=(self.source/builder.MANIFEST).read_bytes()
        original_build=(self.source/builder.BUILD).read_bytes()
        mutations = [
            (lambda m:m['files'][0].update(path='../outside.py'),'PATH_INVALID'),
            (lambda m:m['files'][0].update(path='credentials.json'),'UNCURATED_FILE_REJECTED'),
            (lambda m:m['files'][1].update(path=m['files'][0]['path']),'PATH_COLLISION'),
            (lambda m:m['files'][0].update(git_blob_sha1='0'*40),'FILE_HASH_MISMATCH'),
            (lambda m:m['files'][0].update(bytes=True),'FILE_RECORD_INVALID')]
        for change,code in mutations:
            with self.subTest(code=code):
                (self.source/builder.MANIFEST).write_bytes(original_manifest)
                (self.source/builder.BUILD).write_bytes(original_build)
                self.change_manifest(change)
                with self.assertRaisesRegex(RuntimeError,code): self.identity()

    def test_missing_duplicate_or_oversize_metadata_fails(self):
        path=self.source/builder.BUILD
        original=path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(RuntimeError,'FILE_MISSING_OR_OVERSIZE'): self.identity()
        path.write_bytes(b'{"schema_version":"x","schema_version":"y"}')
        with self.assertRaisesRegex(RuntimeError,'DUPLICATE_JSON_KEY'): self.identity()
        path.write_bytes(b' '*16385)
        with self.assertRaisesRegex(RuntimeError,'FILE_MISSING_OR_OVERSIZE'): self.identity()
        path.write_bytes(original)

    def test_extra_directories_and_reparse_marked_paths_fail_closed(self):
        extra=self.source/'unexpected-empty-runtime'
        extra.mkdir()
        with self.assertRaisesRegex(RuntimeError,'DIRECTORY_INVENTORY_MISMATCH'): self.identity()
        extra.rmdir()
        target=self.source/'src/dragonhydra/future_relevance/service.py'
        original=Path.lstat
        class Reparse:
            st_file_attributes=0x400
        def marked(path,*args,**kwargs):
            return Reparse() if path==target else original(path,*args,**kwargs)
        with (patch.object(Path,'lstat',marked),
              self.assertRaisesRegex(ValueError,'REPARSE_PATH_REJECTED')):
            self.identity()

    def test_git_metadata_prevents_package_fallback_even_if_git_fails(self):
        for metadata in (self.source/'.git', self.source.parent/'.git'):
            with self.subTest(metadata=metadata):
                metadata.write_text('gitdir: nonexistent\n',encoding='utf-8')
                with (patch.object(server.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','fixture failure')),
                      self.assertRaisesRegex(RuntimeError,'SOURCE_IDENTITY_UNAVAILABLE')):
                    server.source_identity()
                metadata.unlink()
        original=Path.lstat
        def denied(path,*args,**kwargs):
            if path==self.source/'.git': raise PermissionError('fictional metadata access denial')
            return original(path,*args,**kwargs)
        with (patch.object(Path,'lstat',denied),
              patch.object(server,'packaged_source_identity',side_effect=AssertionError('DENIAL_IS_NOT_ABSENCE')),
              self.assertRaises(PermissionError)):
            server.source_identity()

    def test_git_identity_requires_exact_root_and_preserves_dirty_truth(self):
        (self.source/'.git').write_text('fixture metadata\n',encoding='utf-8')
        def response(*args,**kwargs):
            command=args[0]
            text=str(self.source) if '--show-toplevel' in command else SHA if 'HEAD' in command else ' M modified.py'
            return subprocess.CompletedProcess(command,0,text+'\n','')
        with patch.object(server.subprocess,'run',side_effect=response):
            result=server.source_identity()
            self.assertEqual(result['source_sha'],SHA)
            self.assertIs(result['source_dirty'],True)
            self.assertNotIn('payload_verified',result)
        with (patch.object(server.subprocess,'run',return_value=subprocess.CompletedProcess([],0,str(self.base),'')),
              self.assertRaisesRegex(RuntimeError,'EXACT_SOURCE_ROOT_REQUIRED')):
            server.source_identity()

    def test_builder_refuses_partial_source_version_case_collision_and_old_output(self):
        for sha,entries,code in [('short',self.entries,'FULL_COMMITTED_SOURCE_REQUIRED'),
                               (SHA,{},'CURATED_REQUIRED_FILES_MISMATCH'),
                               (SHA,{**self.entries,'src/dragonhydra/API.py':b'case'},'PAYLOAD_COUNT_OR_CASE_COLLISION')]:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError,code):
                builder.package_bytes(sha,entries,1700000000)
        wrong={**self.entries,'src/dragonhydra/future_relevance/__init__.py':b'VERSION="wrong"\n'}
        with self.assertRaisesRegex(ValueError,'COMPONENT_VERSION_MISMATCH'):
            builder.package_bytes(SHA,wrong,1700000000)
        output=self.base/'new.zip'
        output.with_suffix('.zip.sha256').write_text('old seal',encoding='ascii')
        with (patch.object(builder,'committed_payload',side_effect=AssertionError('MUST_NOT_COLLECT')),
              self.assertRaisesRegex(ValueError,'NEW_SIDECAR_REQUIRED')):
            builder.main(['--source-root',str(self.source),'--source-commit',SHA,'--output',str(output)])
        self.assertFalse(output.exists())

    def test_builder_refuses_dirty_or_wrong_commit_before_reading_blobs(self):
        def run_dirty(command,**kwargs):
            if '--show-toplevel' in command: out=str(self.source).encode()
            elif 'HEAD' in command: out=SHA.encode()
            elif 'status' in command: out=b' M modified.py'
            else: self.fail('Dirty source reached payload collection')
            return subprocess.CompletedProcess(command,0,out,b'')
        with (patch.object(builder.subprocess,'run',side_effect=run_dirty),
              self.assertRaisesRegex(ValueError,'CLEAN_COMMITTED_SOURCE_REQUIRED')):
            builder.committed_payload(self.source,SHA)

    def test_git_collection_filters_before_blob_reads_and_rechecks_source(self):
        raw=b'# fictional committed source fixture\n'
        oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        records=(f'100644 blob {oid}\tsrc/dragonhydra/api.py\0'
                 f'100644 blob {"0"*40}\tsrc/dragonhydra/resources/data/real.json\0').encode()
        def respond(command,**kwargs):
            if '--show-toplevel' in command: out=str(self.source).encode()
            elif 'HEAD' in command: out=SHA.encode()
            elif 'status' in command: out=b''
            elif 'ls-tree' in command: out=records
            elif 'cat-file' in command:
                self.assertEqual(command[-1],oid,'Excluded real data must never be read')
                out=raw
            elif '--format=%ct' in command: out=b'1700000000'
            else: self.fail('Unexpected Git operation: '+repr(command))
            return subprocess.CompletedProcess(command,0,out,b'')
        with patch.object(builder.subprocess,'run',side_effect=respond):
            entries,timestamp=builder.committed_payload(self.source,SHA)
        self.assertEqual(entries,{'src/dragonhydra/api.py':raw})
        self.assertEqual(timestamp,1700000000)
        statuses=iter([b'',b' M changed.py'])
        def changed(command,**kwargs):
            return subprocess.CompletedProcess(command,0,next(statuses),b'') if 'status' in command else respond(command,**kwargs)
        with (patch.object(builder.subprocess,'run',side_effect=changed),
              self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_COLLECTION')):
            builder.committed_payload(self.source,SHA)


if __name__=='__main__': unittest.main()
