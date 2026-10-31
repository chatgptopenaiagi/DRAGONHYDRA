"""Regression gates for complete frozen-source staging and wheel inspection."""
import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT/'packaging/linux-native/prepare_frozen_bundle.py'
spec = importlib.util.spec_from_file_location('linux_frozen_bundle', TOOL)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class FrozenBundleTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch/linux-frozen-bundle-tests'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def snapshot(self, name, files, key):
        base = self.root/name
        source = base/'source'
        entries = []
        for path, body in sorted(files.items()):
            target = source/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            entries.append({'path':path,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
        content = builder.canonical(entries)
        manifest = base/'SOURCE-MANIFEST.json'
        builder.write_json(manifest, {'source_sha':None,key:content,'files':entries})
        return builder.verify_snapshot(manifest,source,content,key)

    def inputs(self):
        a4 = self.snapshot('a4', {'src/dragonhydra/__init__.py':b'CURRENT_A4=True\n',
                                 'src/dragonhydra/new_only.py':b'NEW_A4=True\n',
                                 'packaging/release/version.json':b'{"version":"same"}'}, 'content_sha256')
        files = {name: ('frozen build support '+name).encode() for name in builder.BUILD_SUPPORT}
        files.update({'src/dragonhydra/__init__.py':b'OLD_APP=True\n',
                      'src/dragonhydra/old_only.py':b'OLD_ONLY=True\n',
                      'packaging/release/version.json':b'{"version":"same"}'})
        support = self.snapshot('support',files,'source_content_sha256')
        return a4,support

    def test_stages_complete_a4_and_never_old_or_live_application(self):
        a4,support = self.inputs()
        destination = self.root/'complete output with spaces'
        manifest = builder.stage_source(a4,support,destination,TOOL)
        self.assertEqual((destination/'src/dragonhydra/__init__.py').read_bytes(),b'CURRENT_A4=True\n')
        self.assertTrue((destination/'src/dragonhydra/new_only.py').is_file())
        self.assertFalse((destination/'src/dragonhydra/old_only.py').exists())
        self.assertEqual(manifest['application_files'],2)
        self.assertEqual(manifest['application_snapshot_sha256'],a4['expected_hash'])
        self.assertEqual(manifest['linux_support_snapshot_sha256'],support['expected_hash'])
        self.assertNotEqual(manifest['source_content_sha256'],a4['expected_hash'])
        self.assertEqual(manifest['source_content_sha256'],builder.canonical(manifest['files']))

    def test_drift_rejected_instead_of_importing_unverified_bytes(self):
        a4,_ = self.inputs()
        (a4['source']/'src/dragonhydra/new_only.py').write_bytes(b'CONCURRENT_CHANGE=True\n')
        with self.assertRaisesRegex(ValueError,'drift'):
            builder.verify_snapshot(a4['manifest_path'],a4['source'],a4['expected_hash'],a4['key'])

    def test_input_changes_during_staging_fail_the_final_whole_origin_check(self):
        a4,support = self.inputs()
        original = builder.checked_copy
        triggered = False
        def mutate_after_copy(source,dest,entry):
            nonlocal triggered
            original(source,dest,entry)
            if not triggered and entry['path']=='src/dragonhydra/new_only.py':
                triggered = True
                Path(source).write_bytes(b'NEW_UNVERIFIED_BYTES=True\n')
        builder.checked_copy = mutate_after_copy
        try:
            with self.assertRaisesRegex(ValueError,'drift'):
                builder.stage_source(a4,support,self.root/'drift-output',TOOL)
        finally:
            builder.checked_copy = original

    def test_private_payload_rejected_even_with_self_consistent_manifest(self):
        for name in ('src/dragonhydra/resources/.env','src/dragonhydra/resources/vault.json',
                     'src/dragonhydra/resources/production.keystore','src/dragonhydra/resources/model.gguf'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,'private'):
                    self.snapshot('private-'+str(len(name)),{name:b'DO_NOT_PACKAGE'},'content_sha256')

    def test_overlapping_support_refused_before_source_is_created(self):
        a4,support = self.inputs()
        destination = self.root/'collision'
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            builder.stage_source(a4,support,destination,TOOL,support_names=('packaging/release/version.json',))
        self.assertFalse(destination.exists())

    def test_existing_staging_is_retained(self):
        a4,support = self.inputs()
        destination = self.root/'existing';destination.mkdir()
        marker = destination/'keep.txt';marker.write_text('KEEP')
        with self.assertRaisesRegex(ValueError,'Preserve'):
            builder.stage_source(a4,support,destination,TOOL)
        self.assertEqual(marker.read_text(),'KEEP')

    def test_traversal_duplicate_and_symlink_rejected(self):
        for name in ('../outside.py','/absolute.py','C:/outside.py','src\\outside.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.safe_relative(name)
        a4,_=self.inputs()
        document=json.loads(a4['manifest_path'].read_text())
        document['files'].append(document['files'][0]);document[a4['key']]=builder.canonical(document['files'])
        builder.write_json(a4['manifest_path'],document)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            builder.verify_snapshot(a4['manifest_path'],a4['source'],document[a4['key']],a4['key'])

    def test_link_does_not_redirect_a_frozen_input(self):
        a4,_=self.inputs();target=a4['source']/'src/dragonhydra/new_only.py'
        elsewhere=self.root/'elsewhere.py';elsewhere.write_bytes(target.read_bytes());target.unlink()
        try:
            target.symlink_to(elsewhere)
        except OSError as error:
            self.skipTest('Host did not permit this isolated symlink fixture: '+str(error))
        with self.assertRaisesRegex(ValueError,'drift'):
            builder.verify_snapshot(a4['manifest_path'],a4['source'],a4['expected_hash'],a4['key'])

    def make_wheel(self,manifest,extra=False,bad_hash=False):
        prefix='dragonhydra-0.4.0a1.dist-info/'
        files={item['path'].removeprefix('src/'):(self.root/'a4/source'/item['path']).read_bytes()
               for item in manifest['files'] if item['path'].startswith('src/dragonhydra/')}
        files['dragonhydra/build_info.json']=json.dumps({'source_sha':None,
            'source_content_sha256':manifest['source_content_sha256'],
            'application_snapshot_sha256':manifest['application_snapshot_sha256']}).encode()
        files[prefix+'METADATA']=b'Metadata-Version: 2.3\nName: dragonhydra\nVersion: 0.4.0a1\nRequires-Python: >=3.14, <3.15\n\n'
        files[prefix+'entry_points.txt']=b'[console_scripts]\ndragon = dragonhydra.packaging_entry:main\ndragonhydra-server = dragonhydra.server:main\n'
        if extra:files['dragonhydra/old_only.py']=b'OLD_SOURCE=True\n'
        rows=[]
        for name,body in sorted(files.items()):
            digest='sha256='+base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip('=')
            rows.append([name,('sha256=WRONG' if bad_hash else digest),str(len(body))])
        rows.append([prefix+'RECORD','','']);out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows)
        files[prefix+'RECORD']=out.getvalue().encode()
        wheel=self.root/('dragonhydra-0.4.0a1-py3-none-any.whl')
        with ZipFile(wheel,'w') as archive:
            for name,body in files.items():archive.writestr(name,body)
        return wheel

    def test_wheel_requires_complete_application_and_accurate_record(self):
        a4,support=self.inputs();manifest=builder.stage_source(a4,support,self.root/'staged',TOOL)
        good=self.make_wheel(manifest)
        self.assertTrue(builder.verify_application_wheel(good,manifest)['passed'])
        with self.assertRaisesRegex(ValueError,'mixed source'):
            builder.verify_application_wheel(self.make_wheel(manifest,extra=True),manifest)
        with self.assertRaisesRegex(ValueError,'RECORD integrity'):
            builder.verify_application_wheel(self.make_wheel(manifest,bad_hash=True),manifest)


if __name__=='__main__':
    unittest.main(verbosity=2)
