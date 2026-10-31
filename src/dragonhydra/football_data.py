"""Import Football-Data.co.uk historical 1X2 prices as labelled source claims.

The CSV does not provide individual quote timestamps. The two column groups are
retained as source-recorded and source-closing labels; they are not live feeds,
proof of synchronized markets or historical system availability.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

from . import market_store

SOURCE_ID = 'football-data-e0-2025-26'
SOURCE_URL = 'https://www.football-data.co.uk/mmz4281/2526/E0.csv'
ATTRIBUTION = 'Football-Data.co.uk'
TRANSFORM_VERSION = 'football-data-e0-prices/1'
FIELDS = {
    'B365': {'source_recorded': ('B365H', 'B365D', 'B365A'),
             'source_close': ('B365CH', 'B365CD', 'B365CA')},
    'PS': {'source_recorded': ('PSH', 'PSD', 'PSA'),
           'source_close': ('PSCH', 'PSCD', 'PSCA')},
}
OUTCOMES = ('home', 'draw', 'away')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _source_event_id(row):
    fields = ('Div', 'Date', 'HomeTeam', 'AwayTeam')
    values = [row.get(k, '').strip() for k in fields]
    if any(not value for value in values) or values[2].casefold() == values[3].casefold():
        raise ValueError('ambiguous source fixture')
    return hashlib.sha256(_canonical(values)).hexdigest()


def _load(path):
    path = Path(path)
    raw = path.read_bytes()
    captured_at = market_store.utc(datetime.now(timezone.utc))
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('invalid source header')
    required = {'Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR'}
    required.update(field for provider in FIELDS.values() for fields in provider.values() for field in fields)
    if not required.issubset(reader.fieldnames):
        raise ValueError('unrecognized Football-Data dataset schema')
    return raw, captured_at, list(reader)


def list_events(path, *, limit=10):
    """List fixture identifiers; original date and time have no assumed timezone."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    raw, captured_at, rows = _load(path)
    events = []
    for row in rows[:limit]:
        events.append({'source_event_id': _source_event_id(row), 'source_date':row['Date'],
                       'source_time':row.get('Time') or None, 'competition':row['Div'],
                       'home':row['HomeTeam'], 'away':row['AwayTeam']})
    return {'source_id':SOURCE_ID, 'source_url':SOURCE_URL, 'source_reference':str(path),
            'source_hash':hashlib.sha256(raw).hexdigest(), 'observed_at':captured_at,
            'source_record_count':len(rows), 'events':events, 'source_attribution':ATTRIBUTION,
            'data_origin':'imported_historical',
            'timing_limit':'No individual quote timestamp or source synchronization proof is supplied.'}


def import_event(db_path, path, source_event_id):
    """Append each labelled 1X2 price as an individual source claim."""
    raw, captured_at, rows = _load(path)
    source_hash = hashlib.sha256(raw).hexdigest()
    matches = [row for row in rows if _source_event_id(row) == str(source_event_id)]
    if len(matches) != 1:
        raise ValueError('source event ID is absent or ambiguous')
    row = matches[0]
    snapshots = []
    for provider, phases in FIELDS.items():
        for phase, fields in phases.items():
            for outcome, field in zip(OUTCOMES, fields):
                quoted = row.get(field, '').strip()
                if not quoted:
                    continue
                snapshots.append({
                    'source_id': SOURCE_ID,
                    'provider_id': 'football-data-label:' + provider,
                    'feed_id': 'football-data-shared-archive',
                    'source_provider_label': provider,
                    'provider_mapping_verified': False,
                    'provider_mapping_basis': 'source column label; provider mapping and independence not independently verified',
                    'adapter_version': TRANSFORM_VERSION,
                    'acquisition_id': ':'.join((source_hash, source_event_id, field)),
                    'data_origin': 'imported_historical',
                    'source_published_at': None,
                    'event_id': 'football-data:' + source_event_id,
                    'competition': row['Div'], 'home': row['HomeTeam'], 'away': row['AwayTeam'],
                    'market_type': '1x2', 'period': 'unknown', 'status': 'unknown',
                    'settlement': 'unknown', 'line': None,
                    'quote_phase': phase, 'quote_time_known': False, 'synchronization_proven': False,
                    'timing_basis': 'source recorded/closing-labelled price; quote time unknown',
                    'source_match_date': row['Date'], 'source_match_time': row.get('Time') or None,
                    'source_result': row.get('FTR') or None, 'result_time_known': False,
                    'source_score_home': row.get('FTHG') or None, 'source_score_away': row.get('FTAG') or None,
                    'source_reference': str(path), 'source_url': SOURCE_URL,
                    'source_column': field, 'source_attribution': ATTRIBUTION,
                    'transformation': TRANSFORM_VERSION + ': source fixture row and named price column',
                    'quotes': [{'outcome': outcome, 'odds_original': quoted, 'odds_format': 'decimal'}],
                })
    if not snapshots:
        raise ValueError('source fixture has no supported labelled prices')
    result = market_store._import_records(db_path, raw, snapshots, captured_at=captured_at)
    result.update({'source_event_id':source_event_id, 'event_id':'football-data:' + source_event_id,
                   'source_url':SOURCE_URL, 'source_attribution':ATTRIBUTION, 'data_origin':'imported_historical',
                   'quote_time_known':False, 'synchronization_proven':False,
                   'timing_limit':'Source price labels do not establish observation times or synchronized markets.',
                   'provider_mapping_verified':False})
    return result
