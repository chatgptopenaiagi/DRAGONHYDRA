"""Adversarial real-SQLite checks using disposable synthetic databases only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.realtime.events import instant
from dragonhydra.realtime.replay import standard_fixture
from dragonhydra.realtime.store import Store


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RealtimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dragonhydra-virtual-store-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.store = Store(self.root / 'research')
        self.match_id = 'virtual-store-match'
        self.store.create_match(self.match_id)
        self.fixture = standard_fixture(self.match_id)

    def counts(self, store=None):
        with (store or self.store).connect() as db:
            return {name: db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                    for name in ('events', 'states', 'forecasts', 'decisions', 'invalidations', 'analyses', 'analysis_intents')}

    def accept_through(self, count):
        return [self.store.accept(event) for event in self.fixture[:count]]

    def custom(self, *, kind='CLOCK', sequence=2, minute=1, source='virtual-source-primary',
               participant='NONE', **attributes):
        raw = deepcopy(self.fixture[0])
        raw.update(event_id='virtual-custom-' + str(sequence) + '-' + source,
                   event_type=kind, sequence=sequence, source_id=source, participant=participant)
        raw['attributes'] = {'minute': minute, **attributes}
        at = instant(self.fixture[0]['event_time']) + timedelta(minutes=minute)
        raw['event_time'] = at.isoformat().replace('+00:00', 'Z')
        raw['received_at'] = (at + timedelta(seconds=2)).isoformat().replace('+00:00', 'Z')
        return raw

    def wrapper(self, revision=1, state_revision=None):
        current = self.store.state(self.match_id)
        return {'forecast_id': 'forecast:virtual-store-' + str(revision), 'match_id': self.match_id,
                'revision': revision, 'state_revision': current['revision'] if state_revision is None else state_revision,
                'forecast': {'synthetic': True, 'full_time_result': {'home': .4, 'draw': .3, 'away': .3}}}

    def test_full_fixture_cancelled_goal_and_card_end_zero_one(self):
        results = [self.store.accept(raw) for raw in self.fixture]
        state = self.store.state(self.match_id)
        self.assertEqual(state['score'], {'home': 0, 'away': 1})
        self.assertEqual(state['red_cards'], {'home': 0, 'away': 0})
        self.assertEqual((state['status'], state['minute'], state['period_end_minute']), ('FINISHED', 95., 95))
        self.assertEqual(state['revision'], len(self.fixture) - 1)
        self.assertEqual(sum(row[1]['action'] == 'DUPLICATE' for row in results), 1)
        self.assertEqual(self.store.metrics()['events_accepted'], len(self.fixture) - 1)

    def test_duplicate_delivery_is_idempotent_but_changed_identity_rejected(self):
        event, _, state = self.store.accept(self.fixture[0])
        duplicate = deepcopy(event)
        duplicate['received_at'] = '2035-01-01T12:00:10Z'
        _, decision, repeated = self.store.accept(duplicate)
        self.assertEqual(decision['action'], 'DUPLICATE')
        self.assertEqual(repeated, state)
        self.assertEqual(self.counts()['events'], 1)
        changed = deepcopy(event)
        changed['attributes']['home_team'] = 'Virtual Changed Team'
        before = self.counts(), self.store.metrics(), self.store.state(self.match_id)
        with self.assertRaisesRegex(ValueError, 'EVENT_IDENTITY_CONFLICT'):
            self.store.accept(changed)
        self.assertEqual((self.counts(), self.store.metrics(), self.store.state(self.match_id)), before)

    def test_event_versions_require_contiguous_chain_and_fixed_identity(self):
        self.accept_through(3)
        shot = deepcopy(self.fixture[2])
        invalid = deepcopy(shot)
        invalid['revision'] = 3
        with self.assertRaisesRegex(ValueError, 'EVENT_REVISION_CHAIN_INVALID'):
            self.store.accept(invalid)
        revised = deepcopy(shot)
        revised['revision'] = 2
        revised['attributes']['on_target'] = False
        self.store.accept(revised)
        state = self.store.state(self.match_id)
        self.assertEqual(state['statistics']['shots']['home'], 1)
        self.assertEqual(state['statistics']['shots_on_target']['home'], 0)
        revised['revision'] = 3
        revised['participant'] = 'AWAY'
        with self.assertRaisesRegex(ValueError, 'EVENT_REVISION_IDENTITY_CHANGED'):
            self.store.accept(revised)

    def test_out_of_order_gap_reconciles_and_prefix_never_contains_future_correction(self):
        self.store.accept(self.fixture[0])
        self.store.accept(self.fixture[4])  # clock, sequence four; missing two/three
        self.assertIn('MISSING_SEQUENCE', self.store.state(self.match_id)['quality']['flags'])
        self.store.accept(self.fixture[1])
        self.store.accept(self.fixture[2])
        self.assertNotIn('MISSING_SEQUENCE', self.store.state(self.match_id)['quality']['flags'])
        for raw in self.fixture[5:]:
            self.store.accept(raw)
        prefix = self.store.events(self.match_id, through_revision=4)
        self.assertEqual({row['event_type'] for row in prefix}, {'KICKOFF', 'CLOCK', 'POSSESSION', 'SHOT'})
        self.assertNotIn('CORRECTION', {row['event_type'] for row in prefix})
        self.assertEqual(self.store.state(self.match_id, 4)['score'], {'home': 0, 'away': 0})
        self.assertEqual(self.store.state(self.match_id)['score'], {'home': 0, 'away': 1})

    def test_late_and_regressed_clock_flags_do_not_move_display_clock_back(self):
        self.store.accept(self.fixture[0])
        self.store.accept(self.custom(sequence=2, minute=10))
        late = self.custom(sequence=3, minute=5)
        late['received_at'] = '2035-01-01T12:15:00Z'
        self.store.accept(late)
        state = self.store.state(self.match_id)
        self.assertEqual(state['minute'], 10.)
        self.assertIn('PROVIDER_CLOCK_REGRESSION', state['quality']['flags'])
        self.assertIn('LATE_EVENT', state['quality']['flags'])

    def test_timezone_equivalent_advancing_clock_is_not_false_regression(self):
        self.store.accept(self.fixture[0])
        offset = self.custom(sequence=2, minute=1)
        offset['event_time'] = '2035-01-01T13:01:00+01:00'
        offset['received_at'] = '2035-01-01T13:01:02+01:00'
        self.store.accept(offset)
        self.store.accept(self.custom(sequence=3, minute=2))
        self.assertNotIn('PROVIDER_CLOCK_REGRESSION', self.store.state(self.match_id)['quality']['flags'])

    def test_secondary_disagreement_does_not_overwrite_primary_score(self):
        self.store.accept(self.fixture[0])
        raw = self.custom(kind='SCORE', sequence=1, minute=0, source='virtual-source-secondary', home=9, away=8)
        self.store.accept(raw)
        state = self.store.state(self.match_id)
        self.assertEqual(state['score'], {'home': 0, 'away': 0})
        self.assertIn('PROVIDER_DISAGREEMENT', state['quality']['flags'])

    def test_irrelevant_observation_avoids_expensive_forecast_but_remains_observed(self):
        self.store.accept(self.fixture[0])
        _, decision, state = self.store.accept(self.fixture[1])
        self.assertEqual(decision['action'], 'STATE_ONLY')
        self.assertEqual(state['statistics']['home_possession_percent'], 53)
        self.assertEqual(self.store.metrics()['expensive_calculations_avoided'], 1)
        self.assertIsNone(decision['expected_information_value'])
        self.assertIn('HEURISTIC_NOT_PROBABILITY', decision['score_kind'])

    def test_suspension_stoppage_reconnect_and_authoritative_final(self):
        self.store.accept(self.fixture[0])
        self.store.accept(self.custom(kind='SUSPEND', sequence=2, minute=10))
        self.assertEqual(self.store.state(self.match_id)['status'], 'SUSPENDED')
        self.store.accept(self.custom(kind='RESUME', sequence=3, minute=10, period=1, period_end_minute=47))
        self.assertEqual(self.store.state(self.match_id)['status'], 'IN_PLAY')
        self.store.accept(self.custom(kind='SOURCE_DISCONNECT', sequence=4, minute=11))
        self.assertFalse(self.store.state(self.match_id)['connected'])
        self.store.accept(self.custom(kind='SOURCE_RECONNECT', sequence=5, minute=12))
        self.assertTrue(self.store.state(self.match_id)['connected'])

    def test_forecast_cas_rejects_stale_calculation_and_preserves_existing_history(self):
        stale = self.wrapper(state_revision=0)
        self.store.accept(self.fixture[0])
        self.assertFalse(self.store.append_forecast(stale))
        self.assertEqual(self.store.timeline(self.match_id), [])
        wrapper = self.wrapper()
        self.assertTrue(self.store.append_forecast(wrapper))
        self.assertTrue(self.store.append_forecast(wrapper))
        self.assertEqual(self.store.metrics()['forecast_updates'], 1)
        changed = deepcopy(wrapper)
        changed['forecast']['full_time_result']['home'] = .5
        with self.assertRaisesRegex(ValueError, 'FORECAST_IDENTITY_CONFLICT'):
            self.store.append_forecast(changed)
        self.assertEqual(self.store.timeline(self.match_id), [wrapper])

    def test_correction_adds_invalidation_without_rewriting_forecast(self):
        self.accept_through(6)
        before = self.wrapper()
        self.store.append_forecast(before)
        correction = next(raw for raw in self.fixture if raw['event_type'] == 'CORRECTION')
        self.store.accept(correction)
        self.assertEqual(self.store.timeline(self.match_id), [before])
        self.assertEqual(self.counts()['invalidations'], 1)
        self.assertEqual(self.store.state(self.match_id)['score']['home'], 0)

    def test_pending_analysis_survives_restart_without_automatic_completion(self):
        packet = {'packet_id': 'virtual-packet-intent', 'match_id': self.match_id, 'synthetic': True}
        self.assertEqual(self.store.analysis_intent(packet), ('NEW', None))
        restarted = Store(self.store.directory)
        self.assertEqual(restarted.analysis_intent(packet), ('UNRESOLVED', None))
        self.assertEqual(restarted.analyses(self.match_id), [])
        result = {'status': 'completed', 'synthetic': True}
        restarted.save_analysis(packet['packet_id'], self.match_id, result)
        self.assertEqual(restarted.analysis_intent(packet), ('COMPLETED', result))

    def test_append_only_sqlite_triggers_execute_on_real_existing_rows(self):
        self.accept_through(6)
        self.store.append_forecast(self.wrapper())
        self.store.accept(next(raw for raw in self.fixture if raw['event_type'] == 'CORRECTION'))
        packet = {'packet_id': 'virtual-intent-immutable', 'match_id': self.match_id}
        self.store.analysis_intent(packet)
        self.store.save_analysis(packet['packet_id'], self.match_id, {'synthetic': True})
        self.store.save_experiment({'synthetic': True, 'result': 'virtual-only'})
        for table in ('events', 'states', 'forecasts', 'decisions', 'invalidations', 'analyses', 'analysis_intents', 'experiments'):
            for action in ('UPDATE', 'DELETE'):
                with self.subTest(table=table, action=action), self.store.connect() as db:
                    self.assertGreater(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
                    sql = ('UPDATE ' + table + ' SET rowid=rowid') if action == 'UPDATE' else ('DELETE FROM ' + table)
                    with self.assertRaisesRegex(sqlite3.DatabaseError, 'IMMUTABLE_RESEARCH_EVIDENCE'):
                        db.execute(sql)

    def test_concurrent_duplicate_delivery_has_one_accepted_fact(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.store.accept, [deepcopy(self.fixture[0]) for _ in range(24)]))
        self.assertEqual(sum(row[1]['action'] != 'DUPLICATE' for row in results), 1)
        self.assertEqual(self.store.state(self.match_id)['revision'], 1)
        self.assertEqual(self.counts()['events'], 1)
        self.assertEqual(self.store.metrics()['duplicates_rejected'], 23)

    def test_retention_limits_fail_before_new_fact(self):
        bounded = Store(self.root / 'bounded', max_events=1, max_matches=1)
        bounded.create_match(self.match_id)
        bounded.accept(self.fixture[0])
        with self.assertRaisesRegex(ValueError, 'EVENT_RETENTION_BUDGET_REACHED'):
            bounded.accept(self.fixture[1])
        self.assertEqual(bounded.state(self.match_id)['revision'], 1)
        with self.assertRaisesRegex(ValueError, 'MATCH_RETENTION_BUDGET_REACHED'):
            bounded.create_match('virtual-second')

    def test_invalid_retention_config_rejected(self):
        for name in ('max_events', 'max_matches'):
            for value in (0, -1, True, 1.5):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    Store(self.root / (name + str(value)), **{name: value})

    def test_foreign_database_rejected_without_byte_or_schema_changes(self):
        for identity in (None, 'foreign-owner/1'):
            directory = self.root / ('foreign-' + str(identity is not None))
            directory.mkdir()
            path = directory / 'virtual-research.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE retained_sentinel(id INTEGER PRIMARY KEY,payload BLOB)')
                db.execute('INSERT INTO retained_sentinel VALUES(1,?)', (b'synthetic protected owner sentinel',))
                if identity is not None:
                    db.execute('CREATE TABLE research_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                    db.execute('INSERT INTO research_meta VALUES(?,?)', ('identity', identity))
                db.commit()
            before = sha(path)
            with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE_REJECTED'):
                Store(directory)
            self.assertEqual(sha(path), before)

    def test_existing_database_file_symlink_rejected_before_following(self):
        directory = self.root / 'linked-db'
        directory.mkdir()
        link = directory / 'virtual-research.sqlite3'
        try:
            os.symlink(self.store.path, link)
        except OSError as exc:
            self.skipTest('Disposable symlink creation unavailable: ' + str(exc.winerror if hasattr(exc, 'winerror') else exc.errno))
        before = sha(self.store.path)
        with self.assertRaisesRegex(ValueError, 'REPARSE_PATH_REJECTED'):
            Store(directory)
        self.assertEqual(sha(self.store.path), before)

    def test_nonempty_unowned_directory_rejected_without_creating_database(self):
        directory = self.root / 'unowned'
        directory.mkdir()
        sentinel = directory / 'retained-owner.json'
        sentinel.write_bytes(b'{"synthetic":true,"owner":"virtual-existing-profile"}')
        before = sha(sentinel)
        with self.assertRaisesRegex(ValueError, 'FOREIGN_RESEARCH_DIRECTORY_REJECTED'):
            Store(directory)
        self.assertEqual(sha(sentinel), before)
        self.assertFalse((directory / 'virtual-research.sqlite3').exists())

    def test_unknown_real_identity_wrong_mode_and_foreign_source_correction_rejected(self):
        with self.assertRaisesRegex(ValueError, 'VIRTUAL_ID_REQUIRED'):
            self.store.create_match('real-record')
        self.store.accept(self.fixture[0])
        bad = deepcopy(self.fixture[1])
        bad['source_mode'] = 'REPLAY'
        with self.assertRaisesRegex(ValueError, 'MATCH_MODE_CONFLICT'):
            self.store.accept(bad)
        self.accept_through(6)
        correction = deepcopy(next(raw for raw in self.fixture if raw['event_type'] == 'CORRECTION'))
        correction['attributes']['target_source_id'] = 'virtual-other-source'
        before = self.counts(), self.store.state(self.match_id)
        with self.assertRaisesRegex(ValueError, 'FOREIGN_SOURCE_CORRECTION_REJECTED'):
            self.store.accept(correction)
        self.assertEqual((self.counts(), self.store.state(self.match_id)), before)

    def test_unrelated_synthetic_retained_sentinel_unchanged(self):
        sentinel = self.root / 'simulated-original.sqlite3'
        with closing(sqlite3.connect(sentinel)) as db:
            db.execute('CREATE TABLE retained(id TEXT,payload BLOB)')
            db.execute('INSERT INTO retained VALUES(?,?)', ('virtual-retained-owner', b'\x00\x01immutable'))
            db.commit()
        before = sha(sentinel)
        self.accept_through(len(self.fixture))
        self.assertEqual(sha(sentinel), before)


if __name__ == '__main__':
    unittest.main()
