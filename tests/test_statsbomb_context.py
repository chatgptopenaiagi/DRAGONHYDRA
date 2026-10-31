"""Exact synthetic StatsBomb parent/receipt bindings, without HTTP or parsing."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra import source_context
from dragonhydra.connectors import research, statsbomb_context as context
from dragonhydra.connectors.core import Document, Transport
from dragonhydra.connectors.store import PROVENANCE_FIELD, digest
from dragonhydra.product import Product


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = '2026-10-31T10:00:00.000000Z'
CATALOG = [{'competition_id':43,'season_id':106,'competition_name':'FIFA World Cup','season_name':'2022'}]
MATCH = {'match_id':3869685,'match_date':'2022-12-18','kick_off':'15:00:00.000',
         'competition':{'competition_id':43,'competition_name':'FIFA World Cup'},
         'season':{'season_id':106,'season_name':'2022'},
         'home_team':{'home_team_id':779,'home_team_name':'Argentina'},
         'away_team':{'away_team_id':771,'away_team_name':'France'},
         'home_score':3,'away_score':3,'match_status':'available',
         'stadium':{'name':'Synthetic retained stadium'},'metadata':{'data_version':'synthetic'}}


class StatsBombContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch',prefix='statsbomb-context-')
        self.addCleanup(self.temp.cleanup)
        self.product = Product(Path(self.temp.name))
        self.path = self.product.db_path
        self.raw = self.product.state/'raw'/'connectors'
        self.raw.mkdir(parents=True)
        self.store = self.product.connector_store
        self.catalog = self.document(CATALOG,research.STATSBOMB_BASE+'competitions.json')
        self.matches = self.document([MATCH],research.STATSBOMB_BASE+'matches/43/106.json')
        class RetainedOnly:
            def get(inner,url):
                return self.catalog if url.endswith('competitions.json') else self.matches
        self.record = research._statsbomb({'competition_id':43,'season_id':106},RetainedOnly(),lambda:None)[0]
        self.assertEqual(self.store.ingest('statsbomb',[self.record],[self.catalog,self.matches])['inserted'],1)
        self.observation_id = self.store.rows('statsbomb')[0]['id']
        self.role_docs = {role:self.document(b'SYNTHETIC '+role.encode()+b' bytes: intentionally unparsed',url)
                          for role,url in context.ROLE_URLS.items()}
        with closing(self.readonly()) as db:
            self.parent = context.parent_binding(db,self.raw,self.observation_id)
            self.bindings = {role:context.document_binding(db,self.raw,role,doc.acquisition_id)
                             for role,doc in self.role_docs.items()}
        self.payload = {'provider':'statsbomb','source_record_id':'3869685','parent':self.parent,
                        'documents':self.bindings,'parser_version':'opaque-binding-test/1',
                        'projection':{'synthetic_binding_only':True}}

    def readonly(self):
        db = sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        db.execute('PRAGMA query_only=ON')
        return db

    def document(self,body,url,**changes):
        raw = body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        resolved = url.replace(research.STATSBOMB_BASE,'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/data/')
        doc = Document(url,resolved,raw,CAPTURE,sha,'application/json',uuid4().hex,sha+'.payload')
        for key,value in changes.items():
            setattr(doc,key,value)
        (self.raw/(sha+'.payload')).write_bytes(raw)
        self.store.receipt('statsbomb',doc)
        return doc

    def validate(self,payload=None):
        with closing(self.readonly()) as db:
            return context.make_binding_validator(self.raw)(db,payload or self.payload)

    def update(self,table,ident,**values):
        with closing(self.product.connect()) as db:
            db.execute('UPDATE '+table+' SET '+','.join(key+'=?' for key in values)+' WHERE id=?',(*values.values(),ident))
            db.commit()

    def legacy(self):
        record = deepcopy(self.record)
        self.update('connector_observations',self.observation_id,record=json.dumps(record),content_hash=digest(record))
        attempt = self.store.start('statsbomb','sync')
        self.store.finish(attempt,result={'provider':'statsbomb','operation':'sync','acquisitions':[
            {'id':doc.acquisition_id,'sha256':doc.sha256,'url':doc.url,'resolved_url':doc.resolved_url,'bytes':len(doc.body)}
            for doc in (self.catalog,self.matches)]})
        with closing(self.readonly()) as db:
            self.parent = context.parent_binding(db,self.raw,self.observation_id)
        self.payload['parent'] = self.parent

    def changed_parent_raw(self,rows):
        doc = self.document(rows,research.STATSBOMB_BASE+'matches/43/106.json')
        record = deepcopy(self.record)
        record['source_document_sha256'] = doc.sha256
        record['original'] = rows[0]
        self.store.ingest('statsbomb',[record],[self.catalog,doc])
        return self.store.rows('statsbomb')[0]['id']

    def test_parent_reconstructed_exact_native_identity_normalized_original_and_receipts(self):
        self.validate()
        self.assertEqual(self.parent['native_identity'],{'match_id':3869685,'competition_id':43,'season_id':106,
            'home_team_id':779,'away_team_id':771,'event_date':'2022-12-18'})
        self.assertEqual(self.parent['normalized_record'],self.record)
        self.assertEqual(self.parent['normalized_record']['original'],MATCH)
        self.assertEqual(self.parent['match_list_acquisition']['id'],self.matches.acquisition_id)
        self.assertEqual(self.parent['catalog_acquisition']['id'],self.catalog.acquisition_id)
        self.assertNotEqual(self.matches.sha256,self.catalog.sha256)

    def test_callbacks_use_supplied_readonly_connection_selects_only_no_network(self):
        statements = []
        with closing(self.readonly()) as db:
            db.set_trace_callback(statements.append)
            with patch.object(Transport,'get',side_effect=AssertionError('HTTP forbidden')):
                context.make_binding_validator(self.raw)(db,self.payload)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements),statements)

    def test_binding_only_accepts_unparsed_bytes_without_claiming_projection_verification(self):
        self.assertNotEqual(self.role_docs['events'].body[:1],b'[')
        self.validate()
        opaque = deepcopy(self.payload)
        opaque['projection'] = {'not_validated_by_this_unit':999999}
        self.validate(opaque)
        self.assertEqual(context.MAX_DOCUMENT_BYTES,8*1024*1024)

    def test_factory_composes_with_source_context_on_isolated_synthetic_state(self):
        receipt = source_context.append(self.path,self.payload,validate_dependencies=context.make_binding_validator(self.raw))
        result = source_context.latest(self.path,'statsbomb','3869685',validate_dependencies=context.make_binding_validator(self.raw))
        self.assertEqual(result['availability'],'available')
        self.assertEqual(result['item']['record_id'],receipt['record_id'])
        self.assertEqual(result['item']['parent'],self.parent)

    def test_legacy_exact_original_cohort_wins_over_newer_same_hash_receipts(self):
        self.legacy()
        repeated = self.document(CATALOG,research.STATSBOMB_BASE+'competitions.json',captured_at='2026-10-31T11:00:00Z')
        self.assertEqual(repeated.sha256,self.catalog.sha256)
        self.validate()
        self.assertEqual(self.parent['catalog_acquisition']['id'],self.catalog.acquisition_id)
        self.assertNotEqual(self.parent['catalog_acquisition']['id'],repeated.acquisition_id)
        self.assertEqual(self.parent['observation_content_hash'],digest(self.record))

    def test_legacy_hash_only_catalog_without_exact_attempt_cohort_rejected(self):
        self.update('connector_observations',self.observation_id,record=json.dumps(self.record),content_hash=digest(self.record))
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'LEGACY_COHORT_UNRESOLVED'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_legacy_conflicting_catalog_cohorts_rejected_instead_of_guessing(self):
        self.legacy()
        repeated = self.document(CATALOG,research.STATSBOMB_BASE+'competitions.json')
        attempt = self.store.start('statsbomb','sync')
        self.store.finish(attempt,result={'provider':'statsbomb','acquisitions':[
            {'id':doc.acquisition_id,'sha256':doc.sha256,'url':doc.url,'resolved_url':doc.resolved_url,'bytes':len(doc.body)}
            for doc in (repeated,self.matches)]})
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'LEGACY_COHORT_UNRESOLVED'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_legacy_cohort_receipt_metadata_mismatch_rejected(self):
        self.legacy()
        self.update('connector_acquisitions',self.catalog.acquisition_id,captured_at='2026-10-31T11:00:00Z')
        # The cohort did not carry capture time, so the canonical parent binding
        # comparison must still detect changing the retained receipt clock.
        with self.assertRaisesRegex(ValueError,'PARENT_BINDING_MISMATCH'):
            self.validate()

    def test_wrong_provider_or_selected_native_match_never_binds(self):
        for field,value in (('provider','nflverse'),('source_record_id','other-native-id')):
            bad = deepcopy(self.payload)
            bad[field] = value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'SELECTION_MISMATCH'):
                self.validate(bad)
        self.update('connector_observations',self.observation_id,source_record_id='3869686')
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_SELECTION_MISMATCH'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_wrong_native_team_competition_season_or_date_in_retained_bytes_rejected(self):
        for field,value in (('home_team',{'home_team_id':780,'home_team_name':'Argentina'}),
                            ('competition',{'competition_id':44}),('season',{'season_id':107}),
                            ('match_date','2022-12-19')):
            with self.subTest(field=field):
                row = deepcopy(MATCH)
                row[field] = value
                observation = self.changed_parent_raw([row])
                with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_NATIVE_IDENTITY_MISMATCH'):
                    context.parent_binding(db,self.raw,observation)

    def test_identical_duplicate_native_rows_in_parent_file_are_not_unique_evidence(self):
        observation = self.changed_parent_raw([MATCH,MATCH])
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_NATIVE_ID_NOT_UNIQUE'):
            context.parent_binding(db,self.raw,observation)

    def test_rehashed_normalized_score_status_original_or_attribute_tampering_rejected(self):
        self.legacy()
        for field,value in (('score_home',8),('status','scheduled'),('original',dict(MATCH,home_score=8)),
                            ('attributes',dict(self.record['attributes'],source_match_status='changed')),
                            ('attributes',dict(self.record['attributes'],retrieved_at=CAPTURE))):
            record = deepcopy(self.record)
            record[field] = value
            self.update('connector_observations',self.observation_id,record=json.dumps(record),content_hash=digest(record))
            with self.subTest(field=field),closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_RECONSTRUCTION_MISMATCH'):
                context.parent_binding(db,self.raw,self.observation_id)

    def test_malformed_persisted_json_shapes_fail_with_validation_errors(self):
        for raw in ('[]','null',json.dumps(dict(self.record,attributes=[])),b'\xff'):
            with self.subTest(raw=raw):
                self.update('connector_observations',self.observation_id,record=raw)
                with closing(self.readonly()) as db,self.assertRaises(ValueError):
                    context.parent_binding(db,self.raw,self.observation_id)

    def test_legacy_cohort_unhashable_ids_fail_with_validation_error(self):
        self.legacy()
        attempt = self.store.start('statsbomb','sync')
        self.store.finish(attempt,result={'provider':'statsbomb','acquisitions':[
            {'id':self.matches.acquisition_id},{'id':{'invalid':'identifier'}}]})
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'LEGACY_COHORT_INVALID'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_parent_row_columns_hash_fk_or_saved_bindings_corruption_rejected(self):
        self.update('connector_observations',self.observation_id,content_hash='0'*64)
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_CONTENT_HASH_MISMATCH'):
            context.parent_binding(db,self.raw,self.observation_id)
        self.update('connector_observations',self.observation_id,content_hash=digest(self.record),status='scheduled')
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_OBSERVATION_METADATA_MISMATCH'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_new_parent_saved_catalog_binding_cannot_switch_to_other_receipt(self):
        record = deepcopy(self.store.rows('statsbomb')[0]['record'])
        binding = record[PROVENANCE_FIELD]['documents'][self.catalog.sha256]['acquisition']
        binding['id'] = self.matches.acquisition_id
        self.update('connector_observations',self.observation_id,record=json.dumps(record))
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_BINDING_METADATA_MISMATCH'):
            context.parent_binding(db,self.raw,self.observation_id)

    def test_exact_role_metadata_hash_clock_url_and_id_are_required(self):
        for field,value in (('id','missing'),('sha256','0'*64),('captured_at','2026-10-31T11:00:00Z'),
                            ('original_url','https://raw.githubusercontent.com/hudl/open-data/master/data/wrong.json'),
                            ('resolved_url','https://raw.githubusercontent.com/hudl/open-data/master/data/wrong.json')):
            bad = deepcopy(self.payload)
            bad['documents']['events'][field] = value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.validate(bad)

    def test_role_wrong_provider_status_or_noncanonical_same_host_url_rejected(self):
        doc = self.role_docs['events']
        for values,code in (({'provider':'nflverse'},'PROVIDER_MISMATCH'),({'http_status':503},'NOT_SUCCESSFUL'),
                            ({'original_url':context.ROLE_URLS['events']+'?other=1'},'ROLE_URL_MISMATCH'),
                            ({'resolved_url':context.ROLE_URLS['events'].replace('/master/','/refs/heads/master/')},'ROLE_URL_MISMATCH')):
            with self.subTest(code=code):
                # Restore from the fixture before applying one independent fault.
                self.update('connector_acquisitions',doc.acquisition_id,provider='statsbomb',http_status=200,
                            original_url=doc.url,resolved_url=doc.resolved_url)
                self.update('connector_acquisitions',doc.acquisition_id,**values)
                with self.assertRaisesRegex(ValueError,code):
                    self.validate()

    def test_missing_corrupt_unsafe_or_oversize_retained_role_bytes_fail_closed(self):
        doc = self.role_docs['events']
        path = self.raw/doc.raw_reference
        path.unlink()
        with self.assertRaisesRegex(ValueError,'RAW_MISSING'):
            self.validate()
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'RAW_INTEGRITY_FAILURE'):
            self.validate()
        path.write_bytes(doc.body)
        self.update('connector_acquisitions',doc.acquisition_id,raw_reference='../outside.payload')
        with self.assertRaisesRegex(ValueError,'RAW_REFERENCE_INVALID'):
            self.validate()
        self.update('connector_acquisitions',doc.acquisition_id,raw_reference=doc.raw_reference,bytes=8*1024*1024+1)
        with self.assertRaisesRegex(ValueError,'PAYLOAD_LIMIT'):
            self.validate()

    def test_actual_file_size_is_bounded_even_if_receipt_size_lies(self):
        doc = self.document(b'x'*65,context.ROLE_URLS['events'])
        self.update('connector_acquisitions',doc.acquisition_id,bytes=32)
        with patch.object(context,'MAX_DOCUMENT_BYTES',64),closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PAYLOAD_LIMIT'):
            context.document_binding(db,self.raw,'events',doc.acquisition_id)

    def test_missing_or_corrupt_catalog_and_match_list_fail_without_context_data(self):
        for doc in (self.catalog,self.matches):
            with self.subTest(doc=doc.url):
                path = self.raw/doc.raw_reference
                path.unlink()
                with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'RAW_MISSING'):
                    context.parent_binding(db,self.raw,self.observation_id)
                path.write_bytes(b'corrupt')
                with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'RAW_INTEGRITY_FAILURE'):
                    context.parent_binding(db,self.raw,self.observation_id)
                path.write_bytes(doc.body)

    def test_metadata_revision_does_not_replace_explicit_old_parent(self):
        row = deepcopy(MATCH)
        row['home_score'] = 4
        self.changed_parent_raw([row])
        self.validate()
        with closing(self.readonly()) as db:
            self.assertEqual(context.parent_binding(db,self.raw,self.observation_id),self.parent)


if __name__ == '__main__':
    unittest.main()
