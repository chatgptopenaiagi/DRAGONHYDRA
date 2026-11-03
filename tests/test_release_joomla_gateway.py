"""Release payload hygiene and commit metadata, independent of live services."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_joomla_gateway',ROOT/'scripts/release_joomla_gateway.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleasePayloadTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'runtime/scratch').mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch',prefix='release-payload-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)

    def test_gateway_allowlist_excludes_live_configuration_and_identifiers(self):
        target=self.directory/'gateway.zip'
        builder.build_gateway(ROOT,target,'test-fixture', 'a'*40)
        with zipfile.ZipFile(target) as archive:
            expected=set(builder.GATEWAY_FILES)|{'README.md','vps/README.md','build-info.json'}
            self.assertEqual(expected,set(archive.namelist()))
            self.assertNotIn('gateway.json',archive.namelist())
            self.assertNotIn('scripts/Test-DragonApacheRecovery.ps1',archive.namelist())
            for name in archive.namelist():
                self.assertFalse(name.startswith('/') or '..' in name.split('/'))
                raw=archive.read(name)
                for private in (b'C:\\Users\\LOVE',b'C:/Users/LOVE',b'C:\\xampp\\DRAGONHYDRA',b'C:/xampp/DRAGONHYDRA',b'metallica-kevin-dangerous-limits',b'188.74.136.7'):
                    self.assertNotIn(private,raw,name)
            info=json.loads(archive.read('build-info.json'))
            self.assertEqual('a'*40,info['source_sha'])
            self.assertEqual('configuration_only_not_deployed',info['permanent_vps'])

    def test_gateway_bytes_repeat_for_identical_controlled_inputs(self):
        first=self.directory/'first.zip';second=self.directory/'second.zip'
        a=builder.build_gateway(ROOT,first,'fixture', 'b'*40)
        b=builder.build_gateway(ROOT,second,'fixture', 'b'*40)
        self.assertEqual(a['sha256'],b['sha256'])
        self.assertEqual(first.read_bytes(),second.read_bytes())

    def test_joomla_payload_embeds_commit_and_installs_metadata_file(self):
        target=self.directory/'joomla.zip'
        result=builder.build_joomla(ROOT,target,'c'*40)
        self.assertEqual(result['source_sha'],'c'*40)
        with zipfile.ZipFile(target) as package:
            self.assertEqual({'pkg_dragonhydra.xml','constituents/com_dragonhydra.zip','constituents/tpl_cassiopeia_dragonhydra.zip'},set(package.namelist()))
            outer = ET.fromstring(package.read('pkg_dragonhydra.xml'))
            self.assertIn('tpl_cassiopeia_dragonhydra.zip', [x.text for x in outer.findall('files/file')])
            with zipfile.ZipFile(io.BytesIO(package.read('constituents/tpl_cassiopeia_dragonhydra.zip'))) as template:
                self.assertEqual({'templateDetails.xml','index.php'},set(template.namelist()))
                details = ET.fromstring(template.read('templateDetails.xml'))
                self.assertEqual('cassiopeia', details.findtext('parent'))
                self.assertEqual(result['version'], details.findtext('version'))
            with zipfile.ZipFile(io.BytesIO(package.read('constituents/com_dragonhydra.zip'))) as component:
                info=json.loads(component.read('admin/build-info.json'))
                self.assertEqual(info['source_sha'],'c'*40)
                self.assertEqual(info['version'],result['version'])
                manifest=ET.fromstring(component.read('dragonhydra.xml'))
                self.assertIn('build-info.json',[x.text for x in manifest.findall('administration/files/filename')])
                self.assertFalse(any(n.endswith(('configuration.php','private.json','.env')) for n in component.namelist()))

    def test_builder_rejects_non_commit_metadata(self):
        with self.assertRaises(ValueError):
            builder.build_gateway(ROOT,self.directory/'bad.zip','fixture','HEAD')
        with self.assertRaises(ValueError):
            builder.build_joomla(ROOT,self.directory/'bad-joomla.zip','HEAD')


if __name__=='__main__':
    unittest.main()
