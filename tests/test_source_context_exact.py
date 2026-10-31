"""Exact immutable context reads isolate the selected predecessor prefix."""
from contextlib import closing
from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch

from dragonhydra import source_context as context
from dragonhydra.cognition import memory
from dragonhydra.connectors import statsbomb_context_parser as parser, statsbomb_context as binding
import test_source_context as fixtures
import test_statsbomb_context_parser as parsed_fixtures


NOW = '2026-10-31T12:00:00.000000Z'
FIRST = fixtures.FIRST
LATER = fixtures.LATER


class ExactContextTests(unittest.TestCase):
    setUp = fixtures.SourceContextTests.setUp
    document = fixtures.SourceContextTests.document
    validate = staticmethod(fixtures.SourceContextTests.validate)
    append = fixtures.SourceContextTests.append
    counts = fixtures.SourceContextTests.counts

    def exact(self,record_id,*,validator=None,now=NOW,**kwargs):
        with patch.object(memory,'_now',return_value=now):
            return context.by_id(self.path,record_id,validate_dependencies=validator or self.validate,**kwargs)

    def revisions(self):
        first = self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        with patch.object(memory,'_now',return_value=LATER):
            second = self.append(changed)
        return first,second

    def rewrite(self,record_id,*,fields=None,natural_key=None,kind=None):
        """Forge independently rehashed data in this private synthetic DB."""
        with closing(sqlite3.connect(self.path)) as db:
            for name in ('cognitive_records_no_update','cognitive_receipts_no_update'):
                db.execute('DROP TRIGGER IF EXISTS '+name)
            row = db.execute('SELECT kind,payload FROM cognitive_records WHERE record_id=?',(record_id,)).fetchone()
            payload = json.loads(row[1])
            payload.update(fields or {})
            key = natural_key or memory._hash(memory._canonical([payload['scope'],payload['revision']]))
            raw = memory._canonical(payload)
            fingerprint = memory._hash(raw)
            node_kind = kind or row[0]
            ident = context.KIND+':'+memory._hash(memory._canonical([node_kind,key,fingerprint]))
            db.execute('UPDATE cognitive_records SET kind=?,record_id=?,natural_key=?,fingerprint=?,payload=? WHERE record_id=?',
                (node_kind,ident,key,fingerprint,raw.decode(),record_id))
            db.execute('UPDATE cognitive_receipts SET record_id=? WHERE record_id=?',(ident,record_id))
            db.commit()
        return ident

    def test_exact_old_version_and_item_shape_survive_later_correction(self):
        first,second = self.revisions()
        older = self.exact(first['record_id'])
        current = self.exact(second['record_id'])
        self.assertEqual(older['availability'],'available')
        self.assertEqual(older['item']['revision'],1)
        self.assertEqual(older['item']['projection']['retained_event_rows'],2)
        self.assertEqual(current['item']['revision'],2)
        self.assertEqual(current['item']['supersedes_record_id'],first['record_id'])
        with patch.object(memory,'_now',return_value=NOW):
            latest = context.latest(self.path,'statsbomb','3869685',validate_dependencies=self.validate)
        self.assertEqual(current,latest)

    def test_full_dependency_validator_runs_once_on_target_not_ancestors(self):
        first,second = self.revisions()
        called = []
        def validate(db,payload):
            called.append(payload['revision'])
            self.validate(db,payload)
        self.assertEqual(self.exact(second['record_id'],validator=validate)['availability'],'available')
        self.assertEqual(called,[2])

    def test_pending_and_corrupt_future_tail_do_not_invalidate_old_record(self):
        first = self.append()
        changed = deepcopy(self.draft)
        changed['projection']['retained_event_rows'] = 3
        with patch.object(memory,'_revision_receipt',side_effect=RuntimeError('fixture record-only crash')):
            with self.assertRaises(RuntimeError):
                self.append(changed)
        self.assertEqual(self.exact(first['record_id'])['availability'],'available')
        with closing(sqlite3.connect(self.path)) as db:
            tail = db.execute('SELECT record_id FROM cognitive_records WHERE record_id<>?',(first['record_id'],)).fetchone()[0]
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.execute("UPDATE cognitive_records SET payload='not JSON' WHERE record_id=?",(tail,))
            db.commit()
        self.assertEqual(self.exact(first['record_id'])['availability'],'available')
        self.assertEqual(self.exact(tail)['availability'],'unavailable')
        self.assertEqual(self.counts(),(2,1))

    def test_later_and_unknown_scope_malformed_rows_are_never_decoded(self):
        first,second = self.revisions()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.execute("UPDATE cognitive_records SET payload='[' WHERE record_id=?",(second['record_id'],))
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',
                (context.KIND,'unrelated-malformed-id','unrelated','broken','not JSON'))
            db.execute("INSERT INTO cognitive_records VALUES('future-kind','unknown','unknown','broken','not JSON')")
            db.commit()
        with patch.object(memory,'_revision_chain',side_effect=AssertionError('whole chain scan forbidden')), \
             patch.object(context,'latest',side_effect=AssertionError('latest forbidden')), \
             patch.object(context,'append',side_effect=AssertionError('append forbidden')), \
             patch.object(context,'recover',side_effect=AssertionError('recovery forbidden')):
            self.assertEqual(self.exact(first['record_id'])['availability'],'available')

    def test_pending_target_fails_without_receipt_repair(self):
        with patch.object(memory,'_revision_receipt',side_effect=RuntimeError('fixture crash')):
            with self.assertRaises(RuntimeError):
                self.append()
        with closing(sqlite3.connect(self.path)) as db:
            ident = db.execute('SELECT record_id FROM cognitive_records').fetchone()[0]
        result = self.exact(ident)
        self.assertEqual(result['code'],'CONTEXT_RECEIPT_PENDING')
        self.assertEqual(self.counts(),(1,0))

    def test_current_clock_and_past_cutoffs_never_substitute_another_version(self):
        first,second = self.revisions()
        self.assertEqual(self.exact(first['record_id'],cutoff=FIRST)['availability'],'available')
        self.assertEqual(self.exact(second['record_id'],cutoff=FIRST)['code'],'CONTEXT_RECEIPT_AFTER_CUTOFF')
        self.assertEqual(self.exact(second['record_id'],now=FIRST)['availability'],'unavailable')
        self.assertEqual(self.exact(second['record_id'],cutoff=LATER)['availability'],'available')
        with patch.object(context,'_connect',side_effect=AssertionError('invalid argument must fail before connection')):
            with self.assertRaisesRegex(ValueError,'CUTOFF_IN_FUTURE'):
                self.exact(first['record_id'],cutoff='2026-11-01T00:00:00Z')

    def test_missing_database_record_and_partial_schema_fail_without_creating_files(self):
        ident = context.KIND+':'+'a'*64
        missing = self.path.parent/'missing.sqlite3'
        with patch.object(memory,'_now',return_value=NOW):
            self.assertEqual(context.by_id(missing,ident,validate_dependencies=self.validate)['code'],'CONTEXT_DATABASE_MISSING')
        self.assertFalse(missing.exists())
        before = self.path.read_bytes()
        self.assertEqual(self.exact(ident)['code'],'CONTEXT_RECORD_NOT_FOUND')
        self.assertEqual(self.path.read_bytes(),before)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE cognitive_records(record_id TEXT)')
        self.assertEqual(self.exact(ident)['code'],'CONTEXT_SCHEMA_INCOMPLETE')

    def test_read_uses_readonly_uri_and_selects_without_schema_helpers(self):
        first,second = self.revisions()
        original = context._connect
        statements = []
        def connect(*args,**kwargs):
            self.assertTrue(kwargs['readonly'])
            db = original(*args,**kwargs)
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
            db.set_trace_callback(statements.append)
            return db
        with closing(sqlite3.connect(self.path)) as db:
            before = db.iterdump()
            before = list(before)
        with patch.object(context,'_connect',side_effect=connect),patch.object(memory,'_schema',side_effect=AssertionError('DDL forbidden')):
            self.assertEqual(self.exact(second['record_id'])['availability'],'available')
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith(('SELECT','BEGIN')) for sql in statements))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(list(db.iterdump()),before)

    def test_validator_is_mandatory_and_cannot_mutate_payload_or_database(self):
        first = self.append()
        with self.assertRaisesRegex(ValueError,'VALIDATOR_REQUIRED'):
            context.by_id(self.path,first['record_id'],validate_dependencies=None)
        for bad in ('',None,'model:'+'a'*64,context.KIND+':'+'A'*64):
            with self.subTest(ident=bad),self.assertRaisesRegex(ValueError,'RECORD_ID_INVALID'):
                context.by_id(self.path,bad,validate_dependencies=self.validate)
        self.assertEqual(self.exact(first['record_id'],validator=lambda db,payload:False)['availability'],'unavailable')
        self.assertEqual(self.exact(first['record_id'],validator=lambda db,payload:db.execute('DELETE FROM parents'))['availability'],'unavailable')
        def mutate(db,payload):
            payload['parent']['observation_id'] = 'rewritten'
        self.assertEqual(self.exact(first['record_id'],validator=mutate)['code'],'CONTEXT_VALIDATOR_MUTATION')
        self.assertEqual(self.counts(),(1,1))

    def test_rehashed_wrong_kind_scope_key_and_numeric_revision_are_rejected(self):
        first = self.append()
        for fields,key,kind,expected in (({},'0'*64,None,'REVISION_KEY_MISMATCH'),
                                        ({'revision':True},None,None,'REVISION_INVALID'),
                                        ({'revision':1.0},None,None,'REVISION_INVALID'),
                                        ({'scope':'f'*64},None,None,'SCOPE_INVALID'),
                                        ({'source_record_id':True},None,None,'INVALID_TEXT'),
                                        ({},None,'model','KIND_MISMATCH')):
            with self.subTest(fields=fields,key=key,kind=kind):
                # Each replacement ID remains self-consistent with its forged
                # canonical bytes; the higher-level identity must still fail.
                ident = self.rewrite(first['record_id'],fields=fields,natural_key=key,kind=kind)
                self.assertIn(expected,self.exact(ident)['code'])
                restored = self.rewrite(ident,fields={'revision':1,'scope':context.scope_key('statsbomb','3869685'),
                    'source_record_id':'3869685'},kind=context.KIND)
                self.assertEqual(restored,first['record_id'])

    def test_gaps_cycles_and_cross_scope_prefixes_fail_closed(self):
        first,second = self.revisions()
        missing = self.rewrite(second['record_id'],fields={'supersedes_record_id':None})
        self.assertIn('GAP',self.exact(missing)['code'])
        restored = self.rewrite(missing,fields={'supersedes_record_id':first['record_id']})
        self.assertEqual(restored,second['record_id'])
        skipped = self.rewrite(restored,fields={'revision':3})
        self.assertIn('GAP',self.exact(skipped)['code'])
        restored = self.rewrite(skipped,fields={'revision':2})
        cycle = self.rewrite(first['record_id'],fields={'supersedes_record_id':first['record_id']})
        self.assertEqual(self.exact(cycle)['availability'],'unavailable')
        # An authentic node of another scope cannot be used as a predecessor.
        original = self.rewrite(cycle,fields={'supersedes_record_id':None})
        foreign_draft = deepcopy(self.draft); foreign_draft['source_record_id'] = 'other-match'
        foreign = self.append(foreign_draft)
        cross = self.rewrite(restored,fields={'supersedes_record_id':foreign['record_id']})
        self.assertEqual(self.exact(cross)['code'],'CONTEXT_PREFIX_SCOPE_MISMATCH')

    def test_corrupt_or_missing_predecessor_fails_but_does_not_replace_target(self):
        first,second = self.revisions()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_update')
            db.execute("UPDATE cognitive_records SET payload='not JSON' WHERE record_id=?",(first['record_id'],))
            db.commit()
        self.assertEqual(self.exact(second['record_id'])['availability'],'unavailable')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_records_no_delete')
            db.execute('DELETE FROM cognitive_records WHERE record_id=?',(first['record_id'],))
            db.commit()
        self.assertEqual(self.exact(second['record_id'])['code'],'CONTEXT_RECORD_NOT_FOUND')

    def test_receipt_order_checked_while_received_starts_may_overlap(self):
        with patch.object(memory,'_now',side_effect=[fixtures.CAPTURE,FIRST,FIRST]):
            first = self.append()
        changed = deepcopy(self.draft); changed['projection']['retained_event_rows'] = 3
        with patch.object(memory,'_now',side_effect=[fixtures.CAPTURE,LATER,LATER]):
            second = self.append(changed)
        self.assertEqual(self.exact(second['record_id'])['availability'],'available')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TRIGGER cognitive_receipts_no_update')
            db.execute('UPDATE cognitive_receipts SET persisted_at=?,usable_at=? WHERE record_id=?',
                ('2026-10-31T10:00:30.000000Z','2026-10-31T10:00:30.000000Z',second['record_id']))
            db.commit()
        self.assertEqual(self.exact(second['record_id'])['code'],'CONTEXT_RECEIPT_CLOCK_INVALID')
        self.assertEqual(self.exact(first['record_id'])['availability'],'available')

    def test_exact_schema_prevents_a_valid_fork_at_the_same_revision(self):
        first = self.append()
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT * FROM cognitive_records').fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',(row[0],'different-id',row[2],row[3],row[4]))
        self.assertEqual(self.exact(first['record_id'])['availability'],'available')

    def test_duplicate_canonical_slot_in_damaged_schema_is_rejected(self):
        first = self.append()
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT * FROM cognitive_records').fetchone()
            receipt = db.execute('SELECT * FROM cognitive_receipts').fetchone()
            for name in ('cognitive_records_no_delete','cognitive_records_no_update','cognitive_receipts_no_delete','cognitive_receipts_no_update'):
                db.execute('DROP TRIGGER '+name)
            db.execute('DROP TABLE cognitive_receipts'); db.execute('DROP TABLE cognitive_records')
            db.execute('CREATE TABLE cognitive_records(kind TEXT,record_id TEXT,natural_key TEXT,fingerprint TEXT,payload TEXT)')
            db.execute('CREATE TABLE cognitive_receipts(record_id TEXT,received_at TEXT,persisted_at TEXT,usable_at TEXT)')
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',row)
            db.execute('INSERT INTO cognitive_receipts VALUES(?,?,?,?)',receipt)
            payload = json.loads(row[4]); payload['projection']['retained_event_rows'] = 99
            raw = memory._canonical(payload); fp = memory._hash(raw)
            ident = context.KIND+':'+memory._hash(memory._canonical([context.KIND,row[2],fp]))
            db.execute('INSERT INTO cognitive_records VALUES(?,?,?,?,?)',(row[0],ident,row[2],fp,raw.decode()))
            db.commit()
        self.assertEqual(self.exact(first['record_id'])['code'],'CONTEXT_IDENTITY_FORK')


class ExactParsedContextTests(unittest.TestCase):
    readonly = parsed_fixtures.BoundParserTests.readonly
    document = parsed_fixtures.BoundParserTests.document
    update = parsed_fixtures.BoundParserTests.update
    setUp = parsed_fixtures.BoundParserTests.setUp

    def exact(self,record_id):
        return context.by_id(self.path,record_id,validate_dependencies=parser.make_validator(self.raw))

    def test_complete_target_survives_ancestor_only_raw_loss_but_own_raw_loss_fails(self):
        validate = parser.make_validator(self.raw)
        first = context.append(self.path,self.payload,validate_dependencies=validate)
        old_events = self.payload['documents']['events']
        rows = deepcopy(parsed_fixtures.EVENTS)+[parsed_fixtures.event(9)]
        doc = self.document(parsed_fixtures.raw(rows),binding.ROLE_URLS['events'])
        changed = deepcopy(self.payload)
        with closing(self.readonly()) as db:
            changed['documents']['events'] = binding.document_binding(db,self.raw,'events',doc.acquisition_id)
        changed['projection'] = parser.parse(parsed_fixtures.raw(rows),parsed_fixtures.raw(parsed_fixtures.LINEUPS),parent=self.parent)
        second = context.append(self.path,changed,validate_dependencies=validate)
        (self.raw/(old_events['sha256']+'.payload')).unlink()
        self.assertEqual(self.exact(second['record_id'])['availability'],'available')
        self.assertEqual(self.exact(first['record_id'])['availability'],'unavailable')
        self.assertEqual(context.latest(self.path,'statsbomb','3869685',validate_dependencies=validate)['availability'],'unavailable')
        (self.raw/doc.raw_reference).unlink()
        self.assertEqual(self.exact(second['record_id'])['availability'],'unavailable')

    def test_rehashed_target_projection_numeric_or_parent_identity_tampering_is_rejected(self):
        validate = parser.make_validator(self.raw)
        first = context.append(self.path,self.payload,validate_dependencies=validate)
        for location in ('count','parent'):
            with closing(sqlite3.connect(self.path)) as db:
                db.execute('DROP TRIGGER IF EXISTS cognitive_records_no_update')
                db.execute('DROP TRIGGER IF EXISTS cognitive_receipts_no_update')
                row = db.execute('SELECT record_id,natural_key,payload FROM cognitive_records').fetchone()
                payload = json.loads(row[2])
                if location == 'count':
                    payload['projection']['event_summary']['row_count'] = 4.0
                else:
                    payload['projection'] = self.payload['projection']
                    payload['parent']['native_identity']['match_id'] = 3869685.0
                raw = memory._canonical(payload); fp = memory._hash(raw)
                ident = context.KIND+':'+memory._hash(memory._canonical([context.KIND,row[1],fp]))
                db.execute('UPDATE cognitive_records SET record_id=?,fingerprint=?,payload=?',(ident,fp,raw.decode()))
                db.execute('UPDATE cognitive_receipts SET record_id=?',(ident,))
                db.commit()
            self.assertEqual(self.exact(ident)['availability'],'unavailable')


if __name__ == '__main__':
    unittest.main()
