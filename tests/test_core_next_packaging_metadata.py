"""A new installer must not ship A9's original-target instructions or identity."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from finalize_core_next_payload import finalize

@unittest.skipUnless(os.name=='nt','Windows private-payload path policy')
class DistributionMetadata(unittest.TestCase):
    def test_candidate_replaces_inherited_instructions_and_component_claims(self):
        lab=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB');testroot=lab/'tests';testroot.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=testroot) as directory:
            work=Path(directory);base=work/'baseline';out=work/'candidate';base.mkdir();out.mkdir()
            (base/'PAYLOAD-MANIFEST.json').write_text(json.dumps({'files':[]}))
            (base/'web').mkdir();(base/'web/payload-manifest.json').write_text(json.dumps({'files':[],'components':{'php':{'version':'8.4.27'}},'runtime_binding':{'bind_address':'127.0.0.1'},'source_sha':'old','joomla_frontend_override':{'path':'C:/xampp/DRAGONHYDRA/old.zip'}}))
            (out/'INSTALLATION.md').write_text('OLD instructions C:\\ProgramData\\DRAGONHYDRA')
            (out/'WORKSTATION-BUILD.json').write_text(json.dumps({'version':'0.4.1-dev.1','source_sha':'old'}))
            for name in ('server/DRAGONHYDRA-Server.exe','client/DRAGONHYDRA-Client.exe','web/extension.zip','web/manage.php','web/CoreNextProfile.php','workstation/DragonhydraService.exe','workstation/DragonhydraLauncher.exe'):
                p=out/name;p.parent.mkdir(exist_ok=True);p.write_bytes(('candidate '+name).encode())
            profile={'environment_id':'candidate','installation_id':'core-next-'+'a'*32,'product':'DRAGONHYDRA CORE NEXT','version':'0.5.0-dev.1','source_commit':'b'*40}
            path=work/'profile.json';path.write_text(json.dumps(profile))
            with patch('finalize_core_next_payload.verify',return_value={'manifest_sha256':'c'*64}):finalize(path,out,base)
            instructions=(out/'INSTALLATION.md').read_text();receipt=json.loads((out/'WORKSTATION-BUILD.json').read_text())
            self.assertIn(profile['source_commit'],instructions)
            self.assertNotIn('C:\\ProgramData\\DRAGONHYDRA',instructions)
            self.assertNotIn('0.4.1-dev.1',instructions)
            self.assertNotIn('{{',instructions)
            self.assertIn('without',instructions)
            self.assertEqual(receipt['source_sha'],profile['source_commit'])
            self.assertEqual(receipt['version'],profile['version'])
            self.assertNotIn(profile['installation_id'],json.dumps(receipt))
            web=json.loads((out/'web/payload-manifest.json').read_text())
            self.assertEqual(web['source_sha'],profile['source_commit'])
            self.assertEqual(web['product_version'],profile['version'])
            self.assertEqual(web['components']['php']['version'],'8.4.27')
            self.assertEqual(web['provisioning_hook']['sha256'],hashlib.sha256((out/'web/manage.php').read_bytes()).hexdigest())
            self.assertEqual(web['joomla_frontend_override']['path'],'extension.zip')
            self.assertNotIn('C:/xampp/DRAGONHYDRA/',json.dumps(web))
            for item in receipt['application_components']:
                self.assertEqual(item['sha256'],hashlib.sha256((out/item['path']).read_bytes()).hexdigest())
            manifest=json.loads((out/'PAYLOAD-MANIFEST.json').read_text())
            for name in ('INSTALLATION.md','WORKSTATION-BUILD.json'):
                self.assertEqual(next(v['sha256'] for v in manifest['files'] if v['path']==name),hashlib.sha256((out/name).read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
