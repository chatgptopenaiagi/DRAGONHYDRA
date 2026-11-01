"""Release guards and existing coordinator draft seam; never contacts GitHub."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('core_next_release',ROOT/'scripts/core_next/release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
LAB=ROOT.parent/(ROOT.name+'-LAB')


class ReleaseGuards(unittest.TestCase):
    def setUp(self):
        folder=LAB/'tests';folder.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='release-guards-',dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name)
        self.tool=release.CoreNextRelease.__new__(release.CoreNextRelease)
        self.tool.root=ROOT;self.tool.lab=LAB;self.tool.assets=self.work
        self.tool.state={'source_sha':'a'*40,'tag':'v0.5.0-dev.1-core-next'}
        self.tool.matrix={'product_version':'0.5.0-dev.1','python_version':'0.5.0.dev1'}

    def test_asset_and_archive_paths_reject_private_state_and_wildcards(self):
        for value in ['../app.exe','all*.exe','report\n.txt','local-session.json','state.sqlite3','signer.pfx']:
            with self.subTest(value=value),self.assertRaises(RuntimeError):release.safe_name(value)
        for members in [['../file'],['C:/state.json'],['state/configuration.php'],['keys/private.pem'],['snapshots/sport.json']]:
            with self.subTest(members=members),self.assertRaises(RuntimeError):release.archive_members(members)
        release.archive_members(['config/runtime/server-python314.lock.txt'])

    def test_paths_and_reference_parser_do_not_accept_original_or_invalid_refs(self):
        with self.assertRaises(RuntimeError):self.tool.local(ROOT.parent/'DRAGONHYDRA/workstation.json')
        self.assertEqual(release.refs('a'*40+'\trefs/tags/new\n'),{'refs/tags/new':'a'*40})
        with self.assertRaises(RuntimeError):release.refs('not-a-git-hash refs/heads/main')

    def test_primary_gate_requires_every_real_witness_and_exact_installer_source(self):
        proof=self.work/'fresh-install-proof.json';proof.write_text('{"passed":true}')
        acceptance={key:{'passed':True,'evidence':[{'path':str(proof),'sha256':release.digest(proof)}]} for key in release.PRIMARY_CHECKS}
        acceptance.update(passed=True,source_commit='a'*40,artifact_sha256='b'*64)
        acceptance['fresh_install']['installation_id']='core-next-'+'c'*32
        path=self.work/'acceptance.json';path.write_text(json.dumps(acceptance))
        self.tool.state['primary_acceptance']=str(path)
        manifest={'artifacts':[{'kind':'workstation','sha256':'b'*64}]}
        self.assertEqual(self.tool.primary_gate(manifest),release.digest(path))
        acceptance['repair']['passed']=False;path.write_text(json.dumps(acceptance))
        with self.assertRaisesRegex(RuntimeError,'gates must pass'):self.tool.primary_gate(manifest)
        acceptance['repair']['passed']=True;path.write_text(json.dumps(acceptance));proof.write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'evidence hash'):self.tool.primary_gate(manifest)

    def test_build_witness_source_and_digest_are_bound(self):
        path=self.work/'build.json';path.write_text(json.dumps({'source_commit':'a'*40,'version':'0.5.0-dev.1'}))
        witness={'path':str(path),'sha256':release.digest(path)}
        self.assertEqual(self.tool.witness(witness)[0]['version'],'0.5.0-dev.1')
        path.write_text(json.dumps({'source_commit':'d'*40}))
        with self.assertRaises(RuntimeError):self.tool.witness(witness)

    def test_wheel_embedded_version_and_source_reject_old_renamed_content(self):
        for source,version,expected in [('a'*40,'0.5.0.dev1',True),('d'*40,'0.5.0.dev1',False),('a'*40,'0.4.0a1',False)]:
            path=self.work/('wheel-'+source[0]+version+'.whl')
            with ZipFile(path,'w') as archive:
                archive.writestr('dragonhydra-0.5.0.dev1.dist-info/METADATA','Name: dragonhydra\nVersion: '+version+'\n')
                archive.writestr('dragonhydra/build_info.json',json.dumps({'source_sha':source,'python_version':version}))
            if expected:self.assertEqual(self.tool.inspect(path,'wheel')['embedded_source_sha'],'a'*40)
            else:
                with self.assertRaises(RuntimeError):self.tool.inspect(path,'wheel')

    def test_joomla_requires_new_version_and_current_embedded_source(self):
        def archive(entries):
            stream=io.BytesIO()
            with ZipFile(stream,'w') as z:
                for name,data in entries.items():z.writestr(name,data)
            return stream.getvalue()
        path=self.work/'joomla.zip'
        component=archive({'dragonhydra.xml':'<extension><version>0.5.0-dev.1</version></extension>',
            'admin/build-info.json':json.dumps({'source_sha':'d'*40})})
        path.write_bytes(archive({'pkg_dragonhydra.xml':'<extension><version>0.5.0-dev.1</version></extension>',
            'constituents/com_dragonhydra.zip':component}))
        with self.assertRaisesRegex(RuntimeError,'embedded source'):self.tool.inspect(path,'joomla')

    def test_existing_publisher_stages_verified_prerelease_without_publishing(self):
        notes=self.work/'RELEASE-NOTES.md';notes.write_text('Reviewed CORE NEXT development notes')
        payload=self.work/'new.exe';payload.write_bytes(b'new owned fixture artifact')
        class Fake(release.Coordinator):
            def __init__(inner):
                inner.state={'repository':'owner/repo','tag':'v0.5.0-dev.1-core-next','source_sha':'a'*40,'title':'CORE NEXT','publication':{}}
                inner.assets=self.work;inner.calls=[];inner.uploaded=False
            def files(inner):return [notes,payload]
            def command(inner,args,**kwargs):return 'a'*40+'\trefs/tags/new^{}'
            def save(inner):pass
            def gh(inner,*args):
                inner.calls.append(args)
                if args[:2]==('release','upload'):inner.uploaded=True
            def release(inner):
                return {'id':123,'draft':True,'prerelease':True,'tag_name':inner.state['tag'],'html_url':'https://example.test/draft','body':notes.read_text(),
                    'assets':([{'name':p.name,'state':'uploaded','size':p.stat().st_size,'digest':'sha256:'+release.digest(p)} for p in [notes,payload]] if inner.uploaded else [])}
        instance=Fake()
        with patch('release_coordinator.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','HTTP 404')):
            instance.publish(draft_only=True)
        self.assertEqual(instance.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')
        self.assertTrue(any('--prerelease' in c and '--latest=false' in c for c in instance.calls))
        self.assertFalse(any('--draft=false' in c or '--clobber' in c for c in instance.calls))


if __name__=='__main__':unittest.main()
