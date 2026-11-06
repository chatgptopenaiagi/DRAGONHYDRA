"""Release guards and existing coordinator draft seam; never contacts GitHub."""
import importlib.util
import copy
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
LAB=release.canonical_lab(ROOT)


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
        with self.assertRaises(RuntimeError):self.tool.local(LAB.parent/'DRAGONHYDRA/workstation.json')
        self.assertEqual(self.tool.local(LAB/'synthetic-input.json'),(LAB/'synthetic-input.json').resolve())
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
                if args[0]=='api':return json.dumps([[]])
                if args[:2]==('release','upload'):inner.uploaded=True
            def release(inner):
                return {'id':123,'draft':True,'prerelease':True,'tag_name':inner.state['tag'],'html_url':'https://example.test/draft','body':notes.read_text(),
                    'assets':([{'name':p.name,'state':'uploaded','size':p.stat().st_size,'digest':'sha256:'+release.digest(p)} for p in [notes,payload]] if inner.uploaded else [])}
        instance=Fake()
        instance.publish(draft_only=True)
        self.assertEqual(instance.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')
        self.assertTrue(any('--prerelease' in c and '--latest=false' in c for c in instance.calls))
        self.assertFalse(any('--draft=false' in c or '--clobber' in c for c in instance.calls))


class HistoryReconciliation(unittest.TestCase):
    """Pure receipt/ref fixtures: no GitHub, refs, registry or application actions."""
    REF='refs/heads/continuity/genesis-20261031-a6'
    LEGACY='c9fcc789d0380bc372cd349d3fb43abcfaeca09f'
    ACCEPTED='a63068de10a111a7784bcf677101a66b693d0908'

    def setUp(self):
        folder=LAB/'tests';folder.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='history-reconciliation-',dir=folder)
        self.addCleanup(self.temp.cleanup);self.work=Path(self.temp.name)
        (self.work/'evidence').mkdir();(self.work/'proof').mkdir()
        self.tool=release.CoreNextRelease.__new__(release.CoreNextRelease)
        self.tool.lab=self.work;self.tool.root=ROOT
        self.tool.state={'source_sha':'a'*40,'repository':'chatgptopenaiagi/DRAGONHYDRA'}
        self.baseline=self.work/'evidence/branches-before.txt'
        self.baseline.write_text(self.LEGACY+'\t'+self.REF+'\n'+'b'*40+'\trefs/heads/main\n')
        self.tags={'refs/tags/older':'c'*40};self.heads={self.REF:self.ACCEPTED,'refs/heads/main':'b'*40}
        (self.work/'evidence/tags-before.txt').write_text(self.ref_text(self.tags))
        audit={'status':'PASS','repository':{'full_name':self.tool.state['repository']},
               'finished_at':{'utc':'2026-11-03T14:29:25.574881Z'},'branches':[{'ref':self.REF,'sha':self.ACCEPTED}]}
        addendum={'coordinator_expected_baseline':self.LEGACY,'actual_tip_at_mission_start':self.ACCEPTED,
                  'current_tip':self.ACCEPTED,'expected_is_ancestor_of_actual':True,'refs_moved_by_this_mission':False,
                  'status':'HISTORY_EVIDENCE_RECORDED_GATE_NOT_ACCEPTED','publication_allowed':False}
        self.audit_path=self.work/'proof/audit.json';self.audit_path.write_text(json.dumps(audit))
        self.addendum_path=self.work/'proof/addendum.json';self.addendum_path.write_text(json.dumps(addendum))
        self.policy={'schema_version':'core-next.history-reconciliation/1','repository':self.tool.state['repository'],
                     'scope':'EXACT_PREMISSION_REF_ONLY','ref':self.REF,'legacy_tip':self.LEGACY,'accepted_tip':self.ACCEPTED,
                     'proofs':{
                         'legacy_baseline':{'path':'evidence/branches-before.txt','sha256':release.digest(self.baseline)},
                         'premission_audit':{'path':'proof/audit.json','sha256':release.digest(self.audit_path),'observed_at':audit['finished_at']['utc']},
                         'unaccepted_addendum':{'path':'proof/addendum.json','sha256':release.digest(self.addendum_path)}}}
        asset={'id':9,'name':'older.zip','size':123,'digest':'sha256:'+'d'*64}
        self.before=[{'id':7,'tag_name':'older','draft':False,'prerelease':False,'published_at':'2026-10-28T00:00:00Z','assets':[asset]}]
        (self.work/'evidence/releases-before.json').write_text(json.dumps(self.before))
        self.after=copy.deepcopy(self.before)
        self.tool.command=self.command;self.tool.gh=self.gh

    @staticmethod
    def ref_text(refs):return ''.join(sha+'\t'+ref+'\n' for ref,sha in refs.items())

    def command(self,args):
        if args==['git','show','a'*40+':packaging/release/history-reconciliation.json']:return json.dumps(self.policy)
        if args==['git','ls-remote','--heads','origin']:return self.ref_text(self.heads)
        if args==['git','ls-remote','--tags','origin']:return self.ref_text(self.tags)
        raise AssertionError('Unexpected command in read-only history fixture')

    def gh(self,*args):
        self.assertEqual(args[0],'api')
        if args[1].endswith('/releases?per_page=100'):return json.dumps(self.after)
        if args[1].endswith('/releases/latest'):return json.dumps({'id':7})
        raise AssertionError('Unexpected API action in read-only history fixture')

    def test_exact_premission_tip_passes_without_changing_baseline(self):
        original=self.baseline.read_bytes();result=self.tool.history()
        self.assertTrue(result['passed']);self.assertEqual(result['historical_assets'],1)
        self.assertEqual(result['history_reconciliation']['accepted_tip'],self.ACCEPTED)
        self.assertFalse(result['history_reconciliation']['future_tip_movement_allowed'])
        self.assertFalse(result['history_reconciliation']['refs_moved'])
        self.assertEqual(self.baseline.read_bytes(),original)

    def test_any_forward_rewind_or_missing_tip_fails(self):
        for value in ['f'*40,self.LEGACY,'0'*40,None]:
            with self.subTest(tip=value):
                if value is None:self.heads.pop(self.REF,None)
                else:self.heads[self.REF]=value
                with self.assertRaisesRegex(RuntimeError,'exact pre-mission tip'):self.tool.history()

    def test_other_branch_and_tag_changes_remain_strict(self):
        self.heads['refs/heads/main']='f'*40
        with self.assertRaisesRegex(RuntimeError,'branches-before.txt refs changed'):self.tool.history()
        self.heads['refs/heads/main']='b'*40;self.tags['refs/tags/older']='f'*40
        with self.assertRaisesRegex(RuntimeError,'tags-before.txt refs changed'):self.tool.history()

    def test_historical_release_classification_assets_and_latest_remain_strict(self):
        self.after[0]['draft']=True
        with self.assertRaisesRegex(RuntimeError,'classification changed'):self.tool.history()
        self.after=copy.deepcopy(self.before);self.after[0]['assets'][0]['digest']='sha256:'+'f'*64
        with self.assertRaisesRegex(RuntimeError,'name/size/digest changed'):self.tool.history()
        self.after=copy.deepcopy(self.before)
        original=self.tool.gh
        self.tool.gh=lambda *args:json.dumps({'id':8}) if args[1].endswith('/latest') else original(*args)
        with self.assertRaisesRegex(RuntimeError,'Stable/latest channel changed'):self.tool.history()

    def test_each_proof_is_hash_bound_and_missing_proof_fails(self):
        for path in [self.baseline,self.audit_path,self.addendum_path]:
            with self.subTest(proof=path.name):
                original=path.read_bytes();path.write_bytes(original+b' ')
                with self.assertRaisesRegex(RuntimeError,'proof hash mismatch'):self.tool.history()
                path.write_bytes(original)
        self.audit_path.unlink()
        with self.assertRaisesRegex(RuntimeError,'proof missing'):self.tool.history()

    def test_frozen_policy_and_semantic_proof_tampering_fail(self):
        cases=[('ref','refs/heads/main'),('accepted_tip','f'*40),('repository','other/repo'),('scope','ALLOW_ANCESTRY')]
        for key,value in cases:
            with self.subTest(field=key):
                original=self.policy[key];self.policy[key]=value
                with self.assertRaises(RuntimeError):self.tool.history()
                self.policy[key]=original
        original=self.audit_path.read_bytes();audit=json.loads(original)
        audit['branches'][0]['sha']='f'*40;self.audit_path.write_text(json.dumps(audit))
        self.policy['proofs']['premission_audit']['sha256']=release.digest(self.audit_path)
        with self.assertRaisesRegex(RuntimeError,'does not prove'):self.tool.history()

    def test_proof_escape_and_addendum_acceptance_rewrite_fail(self):
        original=copy.deepcopy(self.policy)
        for value in ['../outside.json','C:/outside.json','proof\\audit.json']:
            with self.subTest(path=value):
                self.policy['proofs']['premission_audit']['path']=value
                with self.assertRaisesRegex(RuntimeError,'ordinary LAB-relative'):self.tool.history()
        self.policy=original
        addendum=json.loads(self.addendum_path.read_text());addendum['publication_allowed']=True
        self.addendum_path.write_text(json.dumps(addendum))
        self.policy['proofs']['unaccepted_addendum']['sha256']=release.digest(self.addendum_path)
        with self.assertRaisesRegex(RuntimeError,'unaccepted addendum mismatch'):self.tool.history()


if __name__=='__main__':unittest.main()
