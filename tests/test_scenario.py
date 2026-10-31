"""Behavior tests for present-time archival-price scenarios."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dragonhydra import football_data, market_store, scenario


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def evidence(odds='2.20'):
    row = {'Div':'E0', 'Date':'01/08/2025', 'Time':'15:00', 'HomeTeam':'Home',
           'AwayTeam':'Away', 'B365H':odds}
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    raw = stream.getvalue().encode('utf-8')
    source_hash = hashlib.sha256(raw).hexdigest()
    event_id = football_data._source_event_id(row)
    acquisition = ':'.join((source_hash, event_id, 'B365H'))
    identity = json.dumps([football_data.SOURCE_ID, acquisition, 'home'], sort_keys=True,
                          separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    now = datetime.now(timezone.utc)
    quote = {'evidence_id':hashlib.sha256(identity).hexdigest(),
             'source_id':football_data.SOURCE_ID, 'source_hash':source_hash,
             'source_published_at':None, 'acquisition_id':acquisition,
             'provider_id':'football-data-label:B365', 'feed_id':'football-data-shared-archive',
             'source_provider_label':'B365', 'provider_mapping_verified':False, 'adapter_version':football_data.TRANSFORM_VERSION,
             'event_id':'football-data:'+event_id, 'competition':'E0', 'home':'Home', 'away':'Away',
             'market_type':'1x2', 'period':'unknown', 'status':'unknown', 'settlement':'unknown',
             'line':None, 'outcome':'home', 'odds_original':odds, 'odds_format':'decimal',
             'data_origin':'imported_historical', 'clock_mode':'operational',
             'source_column':'B365H', 'source_match_date':'01/08/2025', 'source_match_time':'15:00',
             'quote_phase':'source_recorded', 'quote_time_known':False, 'synchronization_proven':False,
             'received_at':iso(now-timedelta(seconds=3)), 'persisted_at':iso(now-timedelta(seconds=2)),
             'usable_at':iso(now-timedelta(seconds=1))}
    return quote, raw, iso(now)


class ArchivalScenarioTests(unittest.TestCase):
    def setUp(self):
        self.quote, self.raw, self.cutoff = evidence()

    def run_case(self, probability='0.50', **kwargs):
        return scenario.price_scenario(self.quote, probability, self.cutoff, raw_source=self.raw, **kwargs)

    def test_imported_football_data_quote_to_scenario(self):
        root = Path(__file__).resolve().parents[1]
        runtime = root / 'runtime'
        runtime.mkdir(exist_ok=True)
        name = 'test-price-scenario-' + uuid4().hex
        source, db = runtime / (name + '.csv'), runtime / (name + '.sqlite')
        self.addCleanup(source.unlink, missing_ok=True)
        self.addCleanup(db.unlink, missing_ok=True)
        fields = ['Div','Date','Time','HomeTeam','AwayTeam','FTHG','FTAG','FTR']
        fields += [f for provider in football_data.FIELDS.values() for group in provider.values() for f in group]
        row = dict.fromkeys(fields, '2.20')
        row.update(Div='E0', Date='01/08/2025', Time='15:00', HomeTeam='Home',
                   AwayTeam='Away', FTHG='1', FTAG='0', FTR='H')
        with source.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)
        event_id = football_data.list_events(source, limit=1)['events'][0]['source_event_id']
        result = football_data.import_event(db, source, event_id)
        cutoff = iso(datetime.now(timezone.utc))
        quote = next(x for x in market_store.get_as_of(db, cutoff) if x.get('source_column') == 'B365H')
        report = scenario.price_scenario(quote, '0.5', cutoff, raw_source=market_store.raw_source(db, result['source_hash']))
        self.assertEqual(Decimal(report['metrics']['expected_net_return_per_unit']['value']), Decimal('0.10'))
        self.assertEqual(report['quote_evidence']['event_id'], 'football-data:' + event_id)

    def test_exact_expected_value_and_capped_kelly(self):
        result = self.run_case()
        self.assertEqual(scenario.verify_archived_quote(self.quote,self.cutoff,raw_source=self.raw),Decimal('2.20'))
        self.assertEqual(Decimal(result['metrics']['expected_net_return_per_unit']['value']), Decimal('0.10'))
        self.assertEqual(Decimal(result['metrics']['fractional_capped_kelly']['value']), Decimal('0.02'))
        self.assertIn(self.quote['evidence_id'], result['metrics']['expected_net_return_per_unit']['evidence_ids'])
        self.assertIn(result['configuration_evidence']['evidence_id'], result['metrics']['expected_net_return_per_unit']['evidence_ids'])

    def test_probability_parameters_have_present_time_origin(self):
        result = self.run_case()
        config = result['configuration_evidence']
        self.assertEqual(result['replay_mode'], 'PRESENT_TIME_SCENARIO')
        self.assertGreaterEqual(scenario._time(result['scenario_assumed_at']), scenario._time(self.cutoff))
        self.assertEqual(config['received_at'], result['actual_run_time'])
        self.assertEqual(hashlib.sha256(config['canonical_json'].encode('utf-8')).hexdigest(), config['source_hash'])
        self.assertIn('not a probability known at the evidence cutoff', ' '.join(result['uncertainty']))

    def test_scenario_probability_origin_is_hashed(self):
        user = self.run_case(scenario_source='user_supplied')
        default = self.run_case(scenario_source='cli_default')
        self.assertEqual(user['configuration_evidence']['source_id'], 'user-supplied-scenario')
        self.assertEqual(default['configuration_evidence']['source_id'], 'cli-default-scenario')
        self.assertEqual(default['configuration_evidence']['data_origin'], 'configuration')
        self.assertEqual(user['configuration_evidence']['data_origin'], 'user_supplied')
        self.assertNotEqual(user['configuration_evidence']['source_hash'], default['configuration_evidence']['source_hash'])
        with self.assertRaisesRegex(ValueError, 'INVALID_SCENARIO_SOURCE'):
            self.run_case(scenario_source='invented')

    def test_simulation_reproducible_and_sample_variance(self):
        first = self.run_case(trials=20, steps=8, seed=3)
        second = self.run_case(trials=20, steps=8, seed=3)
        self.assertEqual(first['metrics'], second['metrics'])
        self.assertEqual(first['simulation'], second['simulation'])
        self.assertEqual(first['simulation']['trials'], 20)
        self.assertIsNotNone(first['metrics']['sample_variance_final_bankroll']['value'])
        self.assertIsNone(self.run_case(trials=1)['metrics']['sample_variance_final_bankroll']['value'])

    def test_invalid_numbers_and_simulation_budget(self):
        for p in ('NaN', 'Infinity', '-0.1', '1.01'):
            with self.subTest(p=p), self.assertRaises(ValueError):
                self.run_case(p)
        with self.assertRaises(ValueError):
            self.run_case(fraction='1.1')
        with self.assertRaises(ValueError):
            self.run_case(bankroll='0')
        with self.assertRaises(ValueError):
            self.run_case(trials=10000, steps=101)
        with self.assertRaises(ValueError):
            self.run_case(seed=-1)

    def test_exact_cutoff_and_late_arrival(self):
        at_boundary = self.quote['usable_at']
        scenario.price_scenario(self.quote, '0.5', at_boundary, raw_source=self.raw)
        earlier = iso(scenario._time(at_boundary)-timedelta(microseconds=1))
        with self.assertRaisesRegex(ValueError, 'QUOTE_NOT_AVAILABLE_AT_CUTOFF'):
            scenario.price_scenario(self.quote, '0.5', earlier, raw_source=self.raw)

    def test_future_cutoff_rejected(self):
        later = iso(datetime.now(timezone.utc)+timedelta(days=1))
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CUTOFF_IN_FUTURE'):
            scenario.price_scenario(self.quote, '0.5', later, raw_source=self.raw)

    def test_source_hash_and_identity_are_verified(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            scenario.price_scenario(self.quote, '0.5', self.cutoff, raw_source=self.raw+b'x')
        wrong = dict(self.quote, evidence_id='0'*64)
        with self.assertRaisesRegex(ValueError, 'QUOTE_IDENTITY_MISMATCH'):
            scenario.price_scenario(wrong, '0.5', self.cutoff, raw_source=self.raw)

    def test_source_column_price_provider_and_scope_tampering_rejected(self):
        for field, value in [('odds_original','2.40'), ('provider_id','fake'),
                             ('source_column','B365D'), ('quote_phase','source_close'),
                             ('home','Wrong'), ('status','pregame'), ('competition','E1'), ('provider_mapping_verified',True)]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'SOURCE_BINDING_UNPROVED'):
                scenario.price_scenario(dict(self.quote, **{field:value}), '0.5', self.cutoff, raw_source=self.raw)

    def test_simulated_clock_and_unknown_source_cannot_masquerade_as_real(self):
        with self.assertRaisesRegex(ValueError, 'OPERATIONAL_ARCHIVAL_QUOTE_REQUIRED'):
            scenario.price_scenario(dict(self.quote, clock_mode='synthetic_simulated'), '0.5', self.cutoff, raw_source=self.raw)
        bad = dict(self.quote, adapter_version='unknown-adapter')
        with self.assertRaisesRegex(ValueError, 'SOURCE_BINDING_UNPROVED'):
            scenario.price_scenario(bad, '0.5', self.cutoff, raw_source=self.raw)

    def test_conditional_zero_kelly_for_negative_expectation(self):
        result = self.run_case('0.2')
        self.assertLess(Decimal(result['metrics']['expected_net_return_per_unit']['value']), 0)
        self.assertEqual(Decimal(result['metrics']['fractional_capped_kelly']['value']), 0)


if __name__ == '__main__':
    unittest.main()



