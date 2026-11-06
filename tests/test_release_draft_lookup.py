"""Authenticated release-list fixtures only; no GitHub, ledger or native calls."""
import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('draft_lookup_publisher',ROOT/'scripts/release_coordinator.py')
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
TAG='v0.5.0-dev.8-core-next-r2'
SOURCE='2d603431aac0bd86f6ae07e07f124fdfdc0dccce'
API=('api','--paginate','--slurp','repos/owner/repo/releases?per_page=100')
OWNED_API=('api','--header','Cache-Control: no-cache','repos/owner/repo/releases/41')


class ReleaseDraftLookup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='release-draft-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.assets=Path(self.temp.name)
        self.notes=self.assets/'RELEASE-NOTES.md';self.notes.write_text('Reviewed fixture notes',encoding='utf-8')
        self.payload=self.assets/'fixture.bin';self.payload.write_bytes(b'owned fixture bytes')
        self.tool=publisher.Coordinator.__new__(publisher.Coordinator)
        self.tool.assets=self.assets
        self.tool.private=self.assets/'private-evidence';self.tool.private.mkdir()
        self.tool.state={'repository':'owner/repo','tag':TAG,'source_sha':SOURCE,
                         'title':'Fixture prerelease','publication':{}}
        self.tool.files=Mock(return_value=[self.notes,self.payload])
        self.tool.save=Mock()
        self.tool.command=Mock(return_value=SOURCE+'\trefs/tags/'+TAG+'^{}\n')
        # Any accidental native transport is a failure, including Git and gh.
        guard=patch.object(publisher.subprocess,'run',side_effect=AssertionError('NATIVE_OR_NETWORK_CALL_FORBIDDEN'))
        guard.start();self.addCleanup(guard.stop)

    def remote(self,ident=41,tag=TAG,draft=True,assets=None):
        return {'id':ident,'tag_name':tag,'draft':draft,'prerelease':True,
                'assets':[] if assets is None else assets,'body':self.notes.read_text(encoding='utf-8'),
                'html_url':'https://example.test/fixture-release','name':'Fixture prerelease','target_commitish':SOURCE}

    def asset(self,path):
        return {'name':path.name,'state':'uploaded','size':path.stat().st_size,
                'digest':'sha256:'+publisher.digest(path)}

    def listing(self,pages):
        self.tool.gh=Mock(return_value=json.dumps(pages))

    def test_authenticated_exact_draft_is_visible(self):
        remote=self.remote();self.listing([[remote]])
        self.assertEqual(self.tool.find_release(),remote)
        self.tool.gh.assert_called_once_with(*API)
        self.tool.save.assert_not_called()

    def test_published_release_uses_the_same_lookup(self):
        remote=self.remote(draft=False);self.listing([[remote]])
        self.assertEqual(self.tool.release(),remote)

    def test_match_on_later_page_is_found_without_early_absence(self):
        remote=self.remote();self.listing([[self.remote(1,'older')],[self.remote(2,'other')],[remote]])
        self.assertEqual(self.tool.find_release(),remote)
        self.tool.gh.assert_called_once_with(*API)

    def test_successful_empty_listing_establishes_absence(self):
        self.listing([[]])
        self.assertIsNone(self.tool.find_release())

    def test_wrong_tags_including_case_difference_are_not_matches(self):
        self.listing([[self.remote(1,'older')],[self.remote(2,TAG.upper())]])
        self.assertIsNone(self.tool.find_release())

    def test_release_requires_one_and_does_not_return_none(self):
        self.listing([[]])
        with self.assertRaisesRegex(RuntimeError,'absent'):
            self.tool.release()

    def test_duplicate_matching_tags_across_pages_rejected(self):
        self.listing([[self.remote(1)],[self.remote(2)]])
        with self.assertRaisesRegex(RuntimeError,'Multiple releases'):
            self.tool.find_release()

    def test_duplicate_ids_across_pages_rejected_even_for_other_tags(self):
        self.listing([[self.remote(1,'older')],[self.remote(1,'other')]])
        with self.assertRaisesRegex(RuntimeError,'Duplicate release ID'):
            self.tool.find_release()

    def test_malformed_pagination_is_not_absence(self):
        for value in (None,{},[],[{}],[self.remote()],[[None]],[[{}]]):
            with self.subTest(value=value):
                self.listing(value)
                with self.assertRaises(RuntimeError):self.tool.find_release()

    def test_malformed_records_are_rejected_before_returning_a_match(self):
        cases={'id':(True,0,'41'),'tag_name':(None,''),'draft':('true',None),
               'prerelease':(1,None),'assets':({},None),'body':(None,1),'html_url':(None,'')}
        for key,values in cases.items():
            for value in values:
                with self.subTest(field=key,value=value):
                    bad=self.remote(42);bad[key]=value
                    self.listing([[self.remote()],[bad]])
                    with self.assertRaises(RuntimeError):self.tool.find_release()

    def test_invalid_json_and_nontext_transport_are_not_absence(self):
        for value in ('not json','{"message":"denied"}',None):
            with self.subTest(value=value):
                self.tool.gh=Mock(return_value=value)
                with self.assertRaises(RuntimeError):self.tool.find_release()

    def test_network_authentication_and_404_errors_never_create_a_release(self):
        for message in ('network denied','HTTP 403','HTTP 404 repository unavailable'):
            with self.subTest(message=message):
                self.tool.gh=Mock(side_effect=RuntimeError(message))
                with self.assertRaisesRegex(RuntimeError,message):self.tool.publish(draft_only=True)
                self.tool.gh.assert_called_once_with(*API)
                self.tool.save.assert_not_called()
                self.assertEqual(self.tool.state['publication'],{})

    def test_malformed_listing_never_creates_uploads_or_publishes(self):
        self.listing({'message':'malformed'})
        with self.assertRaises(RuntimeError):self.tool.publish(draft_only=True)
        self.tool.gh.assert_called_once_with(*API)
        self.tool.save.assert_not_called()

    def test_foreign_draft_is_never_adopted_uploaded_or_published(self):
        remote=self.remote()
        for ownership in ({},{'release_id':42,'owned_draft':True},{'release_id':41,'owned_draft':False}):
            with self.subTest(ownership=ownership):
                self.tool.state['publication']=copy.deepcopy(ownership)
                self.tool.gh=Mock(side_effect=lambda *args:json.dumps([[remote]] if args==API else remote))
                with self.assertRaisesRegex(RuntimeError,'not created by this release run|Owned release ID/tag'):
                    self.tool.publish(draft_only=True)
                self.assertEqual(self.tool.gh.call_count,1)
                self.assertEqual(self.tool.state['publication'],ownership)
                self.tool.save.assert_not_called()

    def fake_host(self,current,response_target=SOURCE):
        self.host=copy.deepcopy(current);self.actions=[]
        def gh(*args):
            self.actions.append(args)
            if args==API:
                return json.dumps([[],[] if self.host is None else [copy.deepcopy(self.host)]])
            if args[:3]==('api','--method','POST'):
                self.assertIsNone(self.host)
                self.create_payload=json.loads(Path(args[-1]).read_text(encoding='utf-8'))
                self.host=self.remote();self.host['target_commitish']=response_target
                self.raw_create=json.dumps(self.host,indent=2);return self.raw_create
            if args==OWNED_API:
                return json.dumps(copy.deepcopy(self.host))
            if args[:2]==('release','upload'):
                self.host['assets'].append(self.asset(Path(args[-1])));return ''
            if args[:2]==('release','edit'):
                self.assertIn('--draft=false',args);self.assertIn('--prerelease',args);self.assertIn('--latest=false',args)
                self.host['draft']=False;return ''
            raise AssertionError('UNEXPECTED_REMOTE_MUTATION:'+str(args[:2]))
        self.tool.gh=Mock(side_effect=gh)

    def test_new_draft_is_found_after_creation_and_ownership_is_recorded(self):
        self.fake_host(None)
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        self.assertEqual(self.tool.state['publication']['release_id'],41)
        self.assertIs(self.tool.state['publication']['owned_draft'],True)
        self.assertEqual(self.tool.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')
        self.assertEqual(sum(a[:3]==('api','--method','POST') for a in self.actions),1)
        self.assertEqual(sum(a[:2]==('release','upload') for a in self.actions),2)
        self.assertEqual(self.create_payload,{'tag_name':TAG,'target_commitish':SOURCE,'name':'Fixture prerelease',
            'body':self.notes.read_text(encoding='utf-8'),'draft':True,'prerelease':True,'make_latest':'false'})
        self.assertIs(self.create_payload['draft'],True);self.assertIs(self.create_payload['prerelease'],True)
        self.assertEqual((self.tool.private/'draft-create-response.json').read_bytes(),self.raw_create.encode('utf-8'))
        self.assertEqual(sum(a==API for a in self.actions),1)
        self.assertIn(OWNED_API,self.actions)
        self.assertFalse(any('--draft=false' in a or '--clobber' in a for a in self.actions))
        self.tool.files.assert_called_once()

    def test_owned_draft_on_later_page_resumes_only_its_missing_asset(self):
        self.tool.state['publication']={'release_id':41,'owned_draft':True}
        self.fake_host(self.remote(assets=[self.asset(self.notes)]))
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        uploads=[a for a in self.actions if a[:2]==('release','upload')]
        self.assertEqual(len(uploads),1);self.assertEqual(uploads[0][-1],str(self.payload))
        self.assertFalse(any(a[:2] in {('release','create'),('release','edit')} for a in self.actions))
        self.assertNotIn(API,self.actions)
        self.assertFalse((self.tool.private/'draft-create-request.json').exists())
        self.assertEqual(self.tool.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')

    def test_owned_asset_conflict_still_refuses_without_clobber(self):
        self.tool.state['publication']={'release_id':41,'owned_draft':True}
        bad=self.asset(self.notes);bad['digest']='sha256:'+'0'*64
        self.fake_host(self.remote(assets=[bad]))
        with self.assertRaisesRegex(RuntimeError,'no clobber'):
            self.tool.publish(draft_only=True)
        self.assertFalse(any(a[:2] in {('release','create'),('release','upload'),('release','edit')} for a in self.actions))

    def test_annotated_source_tag_guard_still_precedes_lookup(self):
        self.tool.command.return_value='0'*40+'\twrong-source\n';self.listing([[]])
        with self.assertRaisesRegex(RuntimeError,'exact annotated source tag'):
            self.tool.publish(draft_only=True)
        self.tool.gh.assert_not_called()

    def test_failed_file_gate_still_precedes_any_remote_lookup(self):
        self.tool.files.side_effect=RuntimeError('fixture privacy/file gate failure');self.listing([[]])
        with self.assertRaisesRegex(RuntimeError,'privacy/file gate'):
            self.tool.publish(draft_only=True)
        self.tool.command.assert_not_called();self.tool.gh.assert_not_called()

    def test_create_request_is_private_utf8_and_exact_api_payload(self):
        self.notes.write_text('Reviewed Unicode notes \u03a9\n',encoding='utf-8')
        self.fake_host(None)
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        request=self.tool.private/'draft-create-request.json'
        self.assertIn('\u03a9'.encode('utf-8'),request.read_bytes())
        self.assertEqual(self.create_payload['body'],self.notes.read_text(encoding='utf-8'))
        self.assertIn(('api','--method','POST','repos/owner/repo/releases','--input',str(request)),self.actions)

    def test_malformed_partial_or_wrong_create_response_never_owns_or_uploads(self):
        cases=[None,'{partial',json.dumps(None),json.dumps({'id':41})]
        for key,value in (('id',True),('id',0),('tag_name','foreign'),
                          ('name','wrong name'),('body','wrong notes'),('draft',False),('draft','true'),
                          ('prerelease',False),('prerelease','true'),('assets',[{}])):
            record=self.remote();record[key]=value;cases.append(json.dumps(record))
        for index,raw in enumerate(cases):
            with self.subTest(case=index):
                self.tool.private=self.assets/('failed-create-'+str(index));self.tool.private.mkdir()
                self.tool.state['publication']={};self.tool.save.reset_mock();actions=[]
                def gh(*args):
                    actions.append(args)
                    if args==API:return '[[]]'
                    if args[:3]==('api','--method','POST'):return raw
                    raise AssertionError('UNEXPECTED_ACTION_AFTER_INVALID_CREATE')
                self.tool.gh=Mock(side_effect=gh)
                with self.assertRaises(RuntimeError):self.tool.publish(draft_only=True)
                self.assertEqual(self.tool.state['publication'],{});self.tool.save.assert_not_called()
                self.assertEqual(sum(a[:3]==('api','--method','POST') for a in actions),1)
                self.assertTrue((self.tool.private/'draft-create-request.json').is_file())
                response=self.tool.private/'draft-create-response.json';self.assertTrue(response.is_file())
                self.assertEqual(response.read_bytes(),b'' if raw is None else raw.encode('utf-8'))
                with self.assertRaises(FileExistsError):self.tool.publish(draft_only=True)
                self.assertEqual(sum(a[:3]==('api','--method','POST') for a in actions),1)

    def test_unknown_create_transport_outcome_is_preserved_and_cannot_retry(self):
        actions=[]
        def gh(*args):
            actions.append(args)
            if args==API:return '[[]]'
            raise RuntimeError('POST outcome unknown')
        self.tool.gh=Mock(side_effect=gh)
        with self.assertRaisesRegex(RuntimeError,'outcome unknown'):self.tool.publish(draft_only=True)
        request=self.tool.private/'draft-create-request.json';response=self.tool.private/'draft-create-response.json'
        before=(request.read_bytes(),response.read_bytes())
        self.assertEqual(self.tool.state['publication'],{});self.tool.save.assert_not_called()
        with self.assertRaises(FileExistsError):self.tool.publish(draft_only=True)
        self.assertEqual((request.read_bytes(),response.read_bytes()),before)
        self.assertEqual(sum(a[:3]==('api','--method','POST') for a in actions),1)

    def test_existing_response_evidence_blocks_post_without_overwriting(self):
        response=self.tool.private/'draft-create-response.json';response.write_text('preserved unknown response',encoding='utf-8')
        self.listing([[]])
        with self.assertRaises(FileExistsError):self.tool.publish(draft_only=True)
        self.tool.gh.assert_called_once_with(*API)
        self.assertEqual(response.read_text(encoding='utf-8'),'preserved unknown response')
        self.assertEqual(self.tool.state['publication'],{})

    def test_owned_release_uses_fresh_numeric_id_without_a_listing(self):
        remote=self.remote();self.tool.state['publication']={'release_id':41,'owned_draft':True}
        self.tool.gh=Mock(return_value=json.dumps(remote))
        self.assertEqual(self.tool.release(),remote)
        self.tool.gh.assert_called_once_with(*OWNED_API)

    def test_owned_id_tag_and_response_shape_mismatch_never_upload(self):
        cases=[None,'{partial',json.dumps(None),json.dumps(self.remote(42)),json.dumps(self.remote(tag='foreign'))]
        for key,value in (('id',True),('draft','true'),('assets',None),('body',None),('name',None)):
            remote=self.remote();remote[key]=value;cases.append(json.dumps(remote))
        for raw in cases:
            with self.subTest(raw=raw):
                self.tool.state['publication']={'release_id':41,'owned_draft':True};self.tool.save.reset_mock()
                self.tool.gh=Mock(return_value=raw)
                with self.assertRaises(RuntimeError):self.tool.publish(draft_only=True)
                self.tool.gh.assert_called_once_with(*OWNED_API);self.tool.save.assert_not_called()
                self.assertFalse((self.tool.private/'draft-create-request.json').exists())

    def test_owned_id_failure_never_falls_back_to_absence_or_creation(self):
        self.tool.state['publication']={'release_id':41,'owned_draft':True}
        self.tool.gh=Mock(side_effect=RuntimeError('HTTP 404 owned resource unavailable'))
        with self.assertRaisesRegex(RuntimeError,'owned resource unavailable'):self.tool.publish(draft_only=True)
        self.tool.gh.assert_called_once_with(*OWNED_API);self.tool.save.assert_not_called()

    def test_invalid_owned_ledger_id_refuses_before_remote_lookup(self):
        for ident in (None,True,0,'41'):
            with self.subTest(ident=ident):
                self.tool.state['publication']={'release_id':ident,'owned_draft':True};self.tool.gh=Mock()
                with self.assertRaisesRegex(RuntimeError,'Invalid owned release ID'):self.tool.release()
                self.tool.gh.assert_not_called()

    def test_publishing_retains_prerelease_latest_and_owned_id_verification(self):
        self.fake_host(None)
        with redirect_stdout(io.StringIO()):self.tool.publish()
        edits=[a for a in self.actions if a[:2]==('release','edit')]
        self.assertEqual(len(edits),1)
        self.assertIn('--draft=false',edits[0]);self.assertIn('--prerelease',edits[0]);self.assertIn('--latest=false',edits[0])
        self.assertFalse(any('--clobber' in a for a in self.actions))
        self.assertEqual(sum(a==API for a in self.actions),1)
        self.assertEqual(sum(a==OWNED_API for a in self.actions),2)
        self.assertEqual(self.tool.state['publication']['status'],'published_pending_download_verification')

    def test_response_target_metadata_is_informational_not_the_source_gate(self):
        self.fake_host(None,response_target='existing-tag-branch')
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        self.assertEqual(self.create_payload['target_commitish'],SOURCE)
        self.assertEqual(self.host['target_commitish'],'existing-tag-branch')
        self.assertEqual(self.tool.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')
        self.assertEqual(self.tool.command.call_count,2)


if __name__=='__main__':unittest.main()
