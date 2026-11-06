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


class ReleaseDraftLookup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='release-draft-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.assets=Path(self.temp.name)
        self.notes=self.assets/'RELEASE-NOTES.md';self.notes.write_text('Reviewed fixture notes',encoding='utf-8')
        self.payload=self.assets/'fixture.bin';self.payload.write_bytes(b'owned fixture bytes')
        self.tool=publisher.Coordinator.__new__(publisher.Coordinator)
        self.tool.assets=self.assets
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
                'html_url':'https://example.test/fixture-release'}

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
                self.tool.state['publication']=copy.deepcopy(ownership);self.listing([[remote]])
                with self.assertRaisesRegex(RuntimeError,'not created by this release run'):
                    self.tool.publish(draft_only=True)
                self.tool.gh.assert_called_once_with(*API)
                self.assertEqual(self.tool.state['publication'],ownership)
                self.tool.save.assert_not_called()

    def fake_host(self,current):
        self.host=copy.deepcopy(current);self.actions=[]
        def gh(*args):
            self.actions.append(args)
            if args==API:
                return json.dumps([[],[] if self.host is None else [copy.deepcopy(self.host)]])
            if args[:2]==('release','create'):
                self.assertIsNone(self.host);self.host=self.remote();return ''
            if args[:2]==('release','upload'):
                self.host['assets'].append(self.asset(Path(args[-1])));return ''
            raise AssertionError('UNEXPECTED_REMOTE_MUTATION:'+str(args[:2]))
        self.tool.gh=Mock(side_effect=gh)

    def test_new_draft_is_found_after_creation_and_ownership_is_recorded(self):
        self.fake_host(None)
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        self.assertEqual(self.tool.state['publication']['release_id'],41)
        self.assertIs(self.tool.state['publication']['owned_draft'],True)
        self.assertEqual(self.tool.state['publication']['status'],'OWNED_DRAFT_ASSETS_VERIFIED')
        self.assertEqual(sum(a[:2]==('release','create') for a in self.actions),1)
        self.assertEqual(sum(a[:2]==('release','upload') for a in self.actions),2)
        self.assertTrue(any('--prerelease' in a and '--latest=false' in a for a in self.actions))
        self.assertFalse(any('--draft=false' in a or '--clobber' in a for a in self.actions))
        self.tool.files.assert_called_once()

    def test_owned_draft_on_later_page_resumes_only_its_missing_asset(self):
        self.tool.state['publication']={'release_id':41,'owned_draft':True}
        self.fake_host(self.remote(assets=[self.asset(self.notes)]))
        with redirect_stdout(io.StringIO()):self.tool.publish(draft_only=True)
        uploads=[a for a in self.actions if a[:2]==('release','upload')]
        self.assertEqual(len(uploads),1);self.assertEqual(uploads[0][-1],str(self.payload))
        self.assertFalse(any(a[:2] in {('release','create'),('release','edit')} for a in self.actions))
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


if __name__=='__main__':unittest.main()
