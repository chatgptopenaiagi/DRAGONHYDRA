"""Import TipsAudit historical price claims without inventing quote timestamps.

The source supplies opening/closing labels, but no verified publication,
receipt, snapshot-synchronization or provider quote timestamp. Each outcome is
therefore retained as an individual labelled claim. System availability starts
at this import's actual commit acknowledgment, not at kickoff or either label.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from . import market_store

SOURCE_ID = 'tipsaudit-track-record'
SOURCE_URL = 'https://github.com/tipsaudit/track-record-public'
ATTRIBUTION = 'TipsAudit (https://tipsaudit.com); CC BY 4.0'
TRANSFORM_VERSION = 'tipsaudit-historical-quotes/1'


def _load(path):
    path = Path(path)
    raw = path.read_bytes()
    captured_at = market_store.utc(__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text, newline=''))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('invalid source header')
    required = {'id', 'kickoff_utc', 'league', 'home', 'away', 'record_hash'}
    required.update(f'pin_{phase}_{outcome}' for phase in ('open', 'close') for outcome in ('home', 'draw', 'away'))
    if not required.issubset(reader.fieldnames):
        raise ValueError('unrecognized TipsAudit dataset schema')
    return raw, captured_at, list(reader)


def list_events(path, *, limit=10):
    """List source fixtures only; do not infer quote time from kickoff."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    raw, captured_at, rows = _load(path)
    fixtures = [{'source_event_id': row['id'], 'kickoff_utc': row['kickoff_utc'],
                 'competition': row['league'], 'home': row['home'], 'away': row['away']}
                for row in rows[:limit]]
    return {'source_id': SOURCE_ID, 'source_reference': str(path), 'source_hash': hashlib.sha256(raw).hexdigest(),
            'observed_at': captured_at, 'source_record_count': len(rows), 'events': fixtures,
            'source_attribution': ATTRIBUTION, 'data_origin': 'imported_historical',
            'timing_limit': 'Source opening/closing labels have no verified quote timestamps or snapshot synchronization.'}


def import_event(db_path, path, source_event_id):
    """Append one event's individually provider-labelled 1X2 source claims and raw CSV bytes."""
    raw, captured_at, rows = _load(path)
    source_hash = hashlib.sha256(raw).hexdigest()
    matches = [row for row in rows if row.get('id') == str(source_event_id)]
    if len(matches) != 1:
        raise ValueError('source event ID is absent or ambiguous')
    row = matches[0]
    source_event = row['id']
    market_store.utc(row['kickoff_utc'])
    snapshots = []
    skipped_unlabelled_soft = []
    for phase in ('open', 'close', 'best_soft'):
        for outcome in ('home', 'draw', 'away'):
            price_field = f'best_soft_{outcome}' if phase == 'best_soft' else f'pin_{phase}_{outcome}'
            quoted = row.get(price_field, '').strip()
            if not quoted:
                continue
            if phase == 'best_soft':
                source_label = row.get(f'best_soft_book_{outcome}', '').strip()
                if not source_label:
                    skipped_unlabelled_soft.append(outcome)
                    continue
                provider_id = 'unverified-source-label:' + source_label
                mapping_basis = 'provider label as supplied by source; mapping and exchange status unverified'
            else:
                source_label = 'Pinnacle'
                provider_id = 'pinnacle'
                mapping_basis = 'source pin_ field label; provider mapping not independently verified'
            snapshots.append({
                'source_id': SOURCE_ID,
                'provider_id': provider_id,
                'feed_id': 'tipsaudit-source-' + phase,
                'source_provider_label': source_label,
                'provider_mapping_verified': False,
                'provider_mapping_basis': mapping_basis,
                'adapter_version': TRANSFORM_VERSION,
                'acquisition_id': ':'.join((source_hash, source_event, phase, outcome)),
                'data_origin': 'imported_historical',
                'source_published_at': None,
                'event_id': 'tipsaudit:' + source_event,
                'event_at': row['kickoff_utc'],
                'competition': row['league'],
                'home': row['home'],
                'away': row['away'],
                'market_type': '1x2',
                'period': 'unknown',
                'status': 'unknown',
                'settlement': 'unknown',
                'line': None,
                'quote_phase': 'source_' + phase,
                'quote_time_known': False,
                'synchronization_proven': False,
                'timing_basis': 'retrospective source label; quote time unknown',
                'source_reference': str(path),
                'source_record_hash': row['record_hash'],
                'source_result': row.get('result') or None,
                'source_void_reason': row.get('void_reason') or None,
                'result_time_known': False,
                'source_attribution': ATTRIBUTION,
                'source_license': 'CC-BY-4.0',
                'transformation': TRANSFORM_VERSION + ': select CSV row and named source price column',
                'quotes': [{'outcome': outcome, 'odds_original': quoted, 'odds_format': 'decimal'}],
            })
    if not snapshots:
        raise ValueError('source event has no Pinnacle-labelled prices')
    result = market_store._import_records(db_path, raw, snapshots, captured_at=captured_at)
    result.update({'source_event_id':source_event, 'event_id':'tipsaudit:' + source_event,
                   'source_attribution':ATTRIBUTION, 'data_origin':'imported_historical',
                   'quote_time_known':False, 'synchronization_proven':False,
                   'timing_limit':'Opening and closing are source labels, not verified quote timestamps.',
                   'unmapped_provider_labels':True, 'skipped_unlabelled_best_soft_outcomes':skipped_unlabelled_soft})
    return result
