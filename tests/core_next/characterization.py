"""Same fixed fictional inputs for locked A9 and candidate; no live state or network."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import sqlite3
from unittest.mock import patch
from uuid import UUID

AT = '2026-01-20T12:00:00.000000Z'


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 1, 20, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, default=str).encode()).hexdigest()


def characterize():
    from dragonhydra import public_results, research, market_signals, scenario, football_data
    from dragonhydra.cognition import models, evaluation
    fixtures = [
        {'date': '2026-01-01', 'team1': 'A', 'team2': 'C', 'score': {'ft': [2, 0]}},
        {'date': '2026-01-02', 'team1': 'D', 'team2': 'B', 'score': {'ft': [0, 1]}},
        {'date': '2026-01-03', 'team1': 'C', 'team2': 'A', 'score': {'ft': [1, 1]}},
        {'date': '2026-01-04', 'team1': 'B', 'team2': 'D', 'score': {'ft': [2, 2]}},
        {'date': '2026-01-05', 'team1': 'A', 'team2': 'D', 'score': {'ft': [1, 3]}},
        {'date': '2026-01-06', 'team1': 'C', 'team2': 'B', 'score': {'ft': [0, 2]}},
        {'date': '2026-01-25', 'team1': 'A', 'team2': 'B'},
    ]
    db = sqlite3.connect(':memory:')
    try:
        with patch.object(public_results, '_now', return_value=AT), patch.object(models, 'datetime', FrozenDateTime), \
             patch.object(research, 'datetime', FrozenDateTime), patch.object(scenario, 'datetime', FrozenDateTime), \
             patch.object(scenario.uuid, 'uuid4', return_value=UUID('00000000-0000-0000-0000-000000000042')):
            receipt = public_results.ingest_bytes(db, json.dumps({'name': 'Fictional fixed characterization',
                'matches': fixtures}).encode(), source_id='fictional-characterization',
                source_url='fictional:core-next-characterization', acquisition_id='fixed-fixture')
            rows = public_results.latest(db, receipt['usable_at'])
            target = next(row for row in rows if row['result_state'] == 'unavailable')
            forecast = models.forecast(rows, target, AT,
                lambda h: db.execute('SELECT bytes FROM raw_sources WHERE source_hash=?', (h,)).fetchone()[0])
            def quote(eid, price, at, provider='a'):
                return dict(data_origin='synthetic', evidence_id=eid, source_id=provider, provider_id=provider,
                    feed_id=provider, snapshot_id='snap-'+eid, outcome='home', odds_original=price,
                    odds_format='decimal', received_at=at, persisted_at=at, usable_at=at,
                    event_id='fictional-event', competition='fictional-league', home='A', away='B',
                    market_type='1x2', period='full_time', status='pregame', settlement='regulation', line=None)
            signals = market_signals.compute_signals([
                quote('a0', '2.00', '2026-01-20T11:55:00Z'),
                quote('a1', '2.10', '2026-01-20T11:59:00Z'),
                quote('b1', '2.20', '2026-01-20T11:59:30Z', 'b')], AT)
            source = {'Div': 'E0', 'Date': '01/08/2025', 'Time': '15:00', 'HomeTeam': 'Home',
                      'AwayTeam': 'Away', 'B365H': '2.20'}
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=list(source)); writer.writeheader(); writer.writerow(source)
            raw = stream.getvalue().encode()
            source_hash = hashlib.sha256(raw).hexdigest()
            event_id = football_data._source_event_id(source)
            acquisition = ':'.join((source_hash, event_id, 'B365H'))
            eid = hashlib.sha256(json.dumps([football_data.SOURCE_ID, acquisition, 'home'], sort_keys=True,
                separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            archival = dict(evidence_id=eid, source_id=football_data.SOURCE_ID, source_hash=source_hash,
                source_published_at=None, acquisition_id=acquisition, provider_id='football-data-label:B365',
                feed_id='football-data-shared-archive', source_provider_label='B365', provider_mapping_verified=False,
                adapter_version=football_data.TRANSFORM_VERSION, event_id='football-data:'+event_id,
                competition='E0', home='Home', away='Away', market_type='1x2', period='unknown', status='unknown',
                settlement='unknown', line=None, outcome='home', odds_original='2.20', odds_format='decimal',
                data_origin='imported_historical', clock_mode='operational', source_column='B365H',
                source_match_date='01/08/2025', source_match_time='15:00', quote_phase='source_recorded',
                quote_time_known=False, synchronization_proven=False, received_at='2026-01-20T11:59:57Z',
                persisted_at='2026-01-20T11:59:58Z', usable_at='2026-01-20T11:59:59Z')
            risk = scenario.price_scenario(archival, '0.5', AT, raw_source=raw,
                                           trials=120, steps=8, seed=42)
            scores = evaluation._score({'home': '0.5', 'draw': '0.25', 'away': '0.25'}, 'home')
            invalid = []
            for value in ('NaN', 'Infinity', '-1'):
                try:
                    models.poisson_distribution(value)
                except ValueError as error:
                    invalid.append(str(error))
            return {'clock': AT, 'seed': 42, 'forecast_sha256': digest(forecast),
                    'signals_sha256': digest(signals), 'scenario_sha256': digest(risk),
                    'probabilities': {k: v['value'] for k, v in forecast['ensemble']['probabilities'].items()},
                    'poisson': models.poisson_distribution(2.3),
                    'odds': [str(market_signals.convert_odds(v, f)) for v, f in
                             [('2.50', 'decimal'), ('+150', 'american'), ('-110', 'american'), ('5/2', 'fractional')]],
                    'score': scores, 'invalid': invalid}
    finally:
        db.close()
