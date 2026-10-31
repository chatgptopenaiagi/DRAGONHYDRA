"""Synthetic acceptance for context persistence; no StatsBomb HTTP/parsing."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from dragonhydra import source_context as context
from dragonhydra.cognition import memory


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = '2026-10-31T10:00:00.000000Z'
FIRST = '2026-10-31T10:01:00.000000Z'
LATER = '2026-10-31T10:02:00.000000Z'


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='context-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'core.sqlite3'
        with closing(sqlite3.connect(self.path)) as db:
            # Explicit synthetic dependency schema; provider binding/raw parsing
            # integration is deliberately not implemented by this foundation.
            db.executescript('''CREATE TABLE parents(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE documents(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,raw BLOB NOT NULL);''')
            self.parent = {'observation_id':'parent-1', 'source_document_sha256':'a'*64,
                           'native_identity':{'match_id':3869685}}
            db.execute('INSERT INTO parents VALUES(?,?)', ('parent-1',json.dumps(self.parent)))
            db.commit()
        self.documents = {role:self.document(role) for role in context.ROLES}
        self.draft = {'provider':'statsbomb', 'source_record_id':'3869685', 'parent':self.parent,
                      'documents':self.documents, 'parser_version':'synthetic-context/1',
                      'projection':{'retained_event_rows':2}}
        self.clock = patch.object(memory, '_now', return_value=FIRST)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def document(self, role, *, suffix='', raw=None):
        raw = raw or json.dumps({'role':role,'content':suffix}).encode()
        ident = role+suffix
        url = 'https://example.invalid/'+role
        metadata = {'id':ident, 'provider':'statsbomb', 'sha256':hashlib.sha256(raw).hexdigest(),
                    'original_url':url, 'resolved_url':url, 'captured_at':CAPTURE}
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('INSERT INTO documents VALUES(?,?,?)', (ident,json.dumps(metadata),raw))
            db.commit()
        return metadata

    @staticmethod
    def validate(db, payload):
        parent = db.execute('SELECT payload FROM parents WHERE id=?', (payload['parent']['observation_id'],)).fetchone()
        if not parent or json.loads(parent[0]) != payload['parent']:
            raise ValueError('EXACT_PARENT_UNRESOLVED')
        for supplied in payload['documents'].values():
            stored = db.execute('SELECT metadata,raw FROM documents WHERE id=?', (supplied['id'],)).fetchone()
            if (not stored or json.loads(stored[0]) != supplied or
                    hashlib.sha256(stored[1]).hexdigest() != supplied['sha256']):
                raise ValueError('EXACT_DOCUMENT_UNRESOLVED')

    def append(self, draft=None, **kwargs):
        return context.append(self.path, draft or self.draft, validate_dependencies=kwargs.get('validator',self.validate))

    def latest(self, **kwargs):
        return context.latest(self.path,'statsbomb','3869685',validate_dependencies=self.validate, **kwargs)

    def counts(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                         for table in ('cognitive_records','cognitive_receipts'))

    def test_exact_bindings_immutable_receipts_and_schema_reuse(self):
        result = self.append()
        self.assertFalse(result['duplicate'])
        item = self.latest()['item']
        self.assertEqual(item['parent'], self.parent)
        self.assertEqual(item['documents'], self.documents)
        self.assertEqual(item['revision'],1)
        self.assertIsNone(item['supersedes_record_id'])
        self.assertEqual(result['receipt_acknowledged_at'],FIRST)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(len(db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()),4)
            for table in ('cognitive_records','cognitive_receipts'):
                for action in ('UPDATE '+table+' SET record_id=record_id', 'DELETE FROM '+table):
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'immutable cognitive'):
                        db.execute(action)
        self.assertEqual(self.counts(),(1,1))

    def test_same_bytes_new_acquisitions_preserve_original_record_receipt_and_binding(self):
        first = self.append()
        draft = deepcopy(self.draft)
        for role in context.ROLES:
            with closing(sqlite3.connect(self.path)) as db:
                raw = db.execute('SELECT raw FROM documents WHERE id=?',(role,)).fetchone()[0]
            draft['documents'][role] = self.document(role,suffix='-new-capture',raw=raw)
        with patch.object(memory,'_now',return_value=LATER):
            repeated = self.append(draft)
        self.assertTrue(repeated['duplicate'])
        for key in ('record_id','record_content_hash','received_at','persisted_at','usable_at'):
            self.assertEqual(repeated[key],first[key])
        self.assertEqual(self.latest()['item']['documents'],self.documents)
        self.assertEqual(self.counts(),(1,1))

    def test_acknowledgement_clocks_observe_both_durable_commit_boundaries(self):
        observed = []
        clocks = iter((FIRST,LATER,'2026-10-31T10:03:00.000000Z'))
        def clock():
            observed.append(self.counts())
            return next(clocks)
        with patch.object(memory,'_now',side_effect=clock):
            result = self.append()
        self.assertEqual(observed,[(0,0),(1,0),(1,1)])
        self.assertEqual(result['received_at'],FIRST)
        self.assertEqual(result['persisted_at'],LATER)
        self.assertEqual(result['usable_at'],LATER)
        self.assertEqual(result['receipt_acknowledged_at'],'2026-10-31T10:03:00.000000Z')

    def test_latest_semantics_preserve_A_B_A_corrections(self):
        a = self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        b = self.append(changed)
        a_again = self.append()
        self.assertEqual(self.counts(),(3,3))
        self.assertEqual(self.latest()['item']['revision'],3)
        self.assertEqual(self.latest()['item']['supersedes_record_id'],b['record_id'])
        self.assertNotEqual(a_again['record_id'],a['record_id'])

    def test_revision_allocation_is_atomic_for_competing_identical_writers(self):
        barrier = threading.Barrier(6)
        def write(_):
            barrier.wait(timeout=10)
            return self.append()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(write,range(6)))
        self.assertEqual(len({item['record_id'] for item in results}),1)
        self.assertEqual(self.counts(),(1,1))

    def test_competing_changes_make_one_contiguous_predecessor_chain(self):
        self.append()
        barrier = threading.Barrier(4)
        def write(value):
            draft = deepcopy(self.draft)
            draft['projection']['retained_event_rows'] = value
            barrier.wait(timeout=10)
            return self.append(draft)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write,range(3,7)))
        self.assertEqual(self.counts(),(5,5))
        self.assertEqual(self.latest()['item']['revision'],5)

    def pending(self):
        with patch.object(memory,'_revision_receipt',side_effect=RuntimeError('simulated crash after record commit')):
            with self.assertRaisesRegex(RuntimeError,'simulated crash'):
                self.append()
        self.assertEqual(self.counts(),(1,0))

    def test_pending_record_hidden_then_recovered_without_backdating_or_rebinding(self):
        self.pending()
        self.assertEqual(self.latest()['code'],'CONTEXT_RECEIPT_PENDING')
        with patch.object(memory,'_now',return_value=LATER):
            recovered = context.recover(self.path,'statsbomb','3869685',validate_dependencies=self.validate)
        self.assertTrue(recovered['recovered'])
        self.assertEqual(recovered['received_at'],FIRST)
        self.assertEqual(recovered['persisted_at'],LATER)
        self.assertEqual(recovered['receipt_acknowledged_at'],LATER)
        self.assertEqual(self.latest()['item']['documents'],self.documents)
        self.assertEqual(self.counts(),(1,1))
        self.assertEqual(self.latest(cutoff=FIRST)['availability'],'not_requested')

    def test_invalid_pending_binding_blocks_recovery_and_next_revision(self):
        self.pending()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE documents SET raw=X'00' WHERE id='events'")
            db.commit()
        with self.assertRaisesRegex(ValueError,'EXACT_DOCUMENT_UNRESOLVED'):
            context.recover(self.path,'statsbomb','3869685',validate_dependencies=self.validate)
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 7
        with self.assertRaisesRegex(ValueError,'EXACT_DOCUMENT_UNRESOLVED'):
            self.append(changed)
        self.assertEqual(self.counts(),(1,0))

    def test_append_recovers_pending_before_allocating_next_revision(self):
        self.pending()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        with patch.object(memory,'_now',return_value=LATER):
            result = self.append(changed)
        self.assertTrue(result['recovered'])
        self.assertEqual(self.counts(),(2,2))
        self.assertEqual(self.latest()['item']['revision'],2)

    def test_clock_rollback_leaves_durable_pending_then_recovery_preserves_cutoff(self):
        with patch.object(memory,'_now',side_effect=[FIRST,LATER,LATER]):
            first = self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        started = '2026-10-31T10:01:30.000000Z'
        backwards_ack = '2026-10-31T10:01:40.000000Z'
        with patch.object(memory,'_now',side_effect=[started,backwards_ack]):
            with self.assertRaisesRegex(ValueError,'CLOCK_MOVED_BACKWARDS'):
                self.append(changed)
        self.assertEqual(self.counts(),(2,1))
        self.assertEqual(self.latest()['code'],'CONTEXT_RECEIPT_PENDING')
        recovered_at = '2026-10-31T10:03:00.000000Z'
        with patch.object(memory,'_now',return_value=recovered_at):
            recovered = context.recover(self.path,'statsbomb','3869685',validate_dependencies=self.validate)
        self.assertTrue(recovered['recovered'])
        self.assertEqual(recovered['received_at'],started)
        self.assertLess(recovered['received_at'],first['usable_at'])
        self.assertEqual(recovered['usable_at'],recovered_at)
        self.assertEqual(self.latest()['item']['revision'],2)
        self.assertEqual(self.latest(cutoff=LATER)['item']['record_id'],first['record_id'])
        self.assertEqual(self.counts(),(2,2))

    def test_nonmonotonic_receipted_chain_fails_closed_despite_valid_individual_clocks(self):
        with patch.object(memory,'_now',side_effect=[FIRST,LATER,LATER]):
            self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        started = '2026-10-31T10:01:30.000000Z'
        later = '2026-10-31T10:03:00.000000Z'
        with patch.object(memory,'_now',side_effect=[started,later,later]):
            second = self.append(changed)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_receipts_no_update')
            db.execute('UPDATE cognitive_receipts SET persisted_at=?,usable_at=? WHERE record_id=?',
                       ('2026-10-31T10:01:40.000000Z','2026-10-31T10:01:40.000000Z',second['record_id']))
            db.commit()
        self.assertEqual(self.latest()['code'],'MEMORY_RECEIPT_CLOCK_INVALID')
        with self.assertRaisesRegex(ValueError,'MEMORY_RECEIPT_CLOCK_INVALID'):
            self.append()
        self.assertEqual(self.counts(),(2,2))

    def test_old_writer_reuses_receipt_completed_by_concurrent_recovery(self):
        original = memory._revision_receipt
        first = True
        def race(db,kind,scope,record_id,acknowledged,validate):
            nonlocal first
            if first:
                first = False
                context.recover(self.path,'statsbomb','3869685',validate_dependencies=self.validate)
            return original(db,kind,scope,record_id,acknowledged,validate)
        with patch.object(memory,'_revision_receipt',side_effect=race):
            result = self.append()
        self.assertFalse(result['duplicate'])
        self.assertEqual(self.counts(),(1,1))

    def test_bad_incoming_duplicate_is_rejected_and_old_binding_revalidated(self):
        self.append()
        bad = deepcopy(self.draft)
        bad['documents']['events']['id'] = 'missing-new-capture'
        with self.assertRaisesRegex(ValueError,'EXACT_DOCUMENT_UNRESOLVED'):
            self.append(bad)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DELETE FROM parents WHERE id='parent-1'")
            db.commit()
        with self.assertRaisesRegex(ValueError,'EXACT_PARENT_UNRESOLVED'):
            self.append()
        self.assertEqual(self.latest()['availability'],'unavailable')
        self.assertEqual(self.counts(),(1,1))

    def test_read_only_missing_path_no_ddl_no_file_creation_and_partial_schema_honest(self):
        missing = self.path.parent/'missing.sqlite3'
        result = context.latest(missing,'statsbomb','3869685',validate_dependencies=self.validate)
        self.assertEqual(result['availability'],'not_requested')
        self.assertFalse(missing.exists())
        before = self.path.read_bytes()
        self.assertEqual(self.latest()['availability'],'not_requested')
        self.assertEqual(self.path.read_bytes(),before)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE cognitive_records(kind TEXT)')
        self.assertEqual(self.latest()['code'],'CONTEXT_SCHEMA_INCOMPLETE')

    def test_read_does_not_write_and_parent_change_does_not_erase_context(self):
        first = self.append()
        with closing(sqlite3.connect(self.path)) as db:
            before = db.execute('SELECT * FROM cognitive_records').fetchall(),db.execute('SELECT * FROM cognitive_receipts').fetchall()
        statements = []
        connect = context._connect
        def traced(*args,**kwargs):
            db = connect(*args,**kwargs)
            db.set_trace_callback(statements.append)
            return db
        with patch.object(context,'_connect',side_effect=traced):
            read = self.latest(parent_observation_id='parent-new-metadata')
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT','BEGIN')) for sql in statements),statements)
        self.assertEqual(read['availability'],'parent_changed')
        self.assertEqual(read['item']['record_id'],first['record_id'])
        self.assertEqual(self.latest()['availability'],'available')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(before,(db.execute('SELECT * FROM cognitive_records').fetchall(),db.execute('SELECT * FROM cognitive_receipts').fetchall()))

    def test_cognition_six_kind_shape_and_evidence_resolution_ignore_context_and_unknown_kinds(self):
        first = self.append()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO cognitive_records VALUES('future-kind','future','future','invalid','not JSON')")
            db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)',('future',FIRST,FIRST,FIRST))
            db.commit()
            result = memory._as_of(db,FIRST)
            self.assertEqual(set(result),{'models','predictions','outcomes','research_tasks','evaluations','hypotheses'})
            self.assertTrue(all(value == [] for value in result.values()))
            # Context is not accidentally exposed as a model-state record.
            with patch.object(memory,'_source_rows',return_value={}),patch.object(memory,'_market_evidence',return_value=None):
                self.assertIsNone(memory._resolve_evidence(db,first['record_id'],FIRST))
        self.assertEqual(self.latest()['availability'],'available')

    def test_dependency_validator_required_read_only_boolean_and_mutation_guards(self):
        with self.assertRaisesRegex(ValueError,'VALIDATOR_REQUIRED'):
            self.append(validator=None)
        with self.assertRaisesRegex(ValueError,'VALIDATION_FAILED'):
            self.append(validator=lambda db,payload:False)
        with self.assertRaisesRegex(sqlite3.DatabaseError,'not authorized'):
            self.append(validator=lambda db,payload:db.execute('DELETE FROM parents'))
        def mutate(db,payload):
            payload['parent']['observation_id'] = 'rewritten'
        with self.assertRaisesRegex(ValueError,'VALIDATOR_MUTATION'):
            self.append(validator=mutate)
        self.assertEqual(self.counts(),(0,0))

    def test_cross_provider_duplicate_documents_and_reserved_fields_rejected(self):
        cases = []
        wrong = deepcopy(self.draft)
        wrong['documents']['events']['provider'] = 'another-provider'
        cases.append((wrong,'PROVIDER_MISMATCH'))
        wrong = deepcopy(self.draft)
        wrong['documents']['lineups'] = wrong['documents']['events']
        cases.append((wrong,'DISTINCT_DOCUMENTS'))
        wrong = dict(self.draft,revision=17)
        cases.append((wrong,'DRAFT_REQUIRED'))
        for draft,code in cases:
            with self.subTest(code=code),self.assertRaisesRegex(ValueError,code):
                self.append(draft)

    def test_corrupt_middle_revision_never_selects_or_appends_after_old_head(self):
        self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        self.append(changed)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.execute("UPDATE cognitive_records SET payload=replace(payload,'\"revision\":1','\"revision\":9') WHERE payload LIKE '%\"revision\":1%'")
            db.commit()
        self.assertEqual(self.latest()['code'],'MEMORY_CONTENT_HASH_MISMATCH')
        with self.assertRaisesRegex(ValueError,'MEMORY_CONTENT_HASH_MISMATCH'):
            self.append()
        self.assertEqual(self.counts(),(2,2))

    def test_corrupt_head_scope_is_verified_before_scope_exclusion(self):
        self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        self.append(changed)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            rows = db.execute('SELECT record_id,payload FROM cognitive_records').fetchall()
            head_id,raw = next((ident,raw) for ident,raw in rows if json.loads(raw)['revision'] == 2)
            payload = json.loads(raw)
            payload['scope'] = '0'*64
            db.execute('UPDATE cognitive_records SET payload=? WHERE record_id=?',
                       (memory._canonical(payload).decode(),head_id))
            db.commit()
        self.assertEqual(self.latest()['code'],'MEMORY_CONTENT_HASH_MISMATCH')
        with self.assertRaisesRegex(ValueError,'MEMORY_CONTENT_HASH_MISMATCH'):
            self.append()
        self.assertEqual(self.counts(),(2,2))


if __name__ == '__main__':
    unittest.main()
