"""Bounded, offline polling of a local snapshot file.

Each changed file is read once and its exact bytes are committed by the normal
operational ingestion path. Source acquisition IDs are never rewritten. A
conflicting reused ID is quarantined. No watcher timestamps are backdated.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import time
import uuid

from . import market_store

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'local-snapshot-watch/1'


def _inside(path):
    value = Path(path).resolve()
    if not value.is_relative_to(ROOT):
        raise ValueError('path must be inside the DRAGONHYDRA workspace')
    return value


def watch_file(db_path, path, *, iterations=1, interval_seconds=1,
               sleeper=None, reader=None, on_poll=None):
    """Poll a local JSON/CSV snapshot at most ``iterations`` times.

    The reader and sleeper parameters support deterministic tests. Acquisition
    identity and origin remain the source's explicit claims. All observations
    use actual operational read and persistence-acknowledgment clocks; a
    synthetic input label cannot activate a synthetic clock here.
    """
    if type(iterations) is not int or not 1 <= iterations <= 1000:
        raise ValueError('iterations must be an integer between 1 and 1000')
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
        raise ValueError('invalid interval')
    if not 0 <= interval_seconds <= 60 or not math.isfinite(interval_seconds):
        raise ValueError('interval must be finite and between 0 and 60 seconds')
    if iterations * interval_seconds > 3600:
        raise ValueError('requested watch duration exceeds one hour')
    path = _inside(path)
    db_path = _inside(db_path)
    if path.suffix.lower() not in ('.json', '.csv'):
        raise ValueError('snapshot file must be JSON or CSV')
    if sleeper is None:
        sleeper = time.sleep
    if reader is None:
        reader = lambda source: source.read_bytes()
    if not callable(sleeper) or not callable(reader) or (on_poll is not None and not callable(on_poll)):
        raise ValueError('reader, sleeper and on_poll must be callable')
    if not db_path.parent.is_dir():
        raise ValueError('database directory must already exist')
    events = []
    tasks = []
    previous_hash = None
    for number in range(1, iterations + 1):
        try:
            raw = reader(path)
            observed_at = market_store.utc(datetime.now(timezone.utc))
            if not isinstance(raw, bytes):
                raise ValueError('reader must return bytes')
        except (OSError, ValueError) as exc:
            observed_at = market_store.utc(datetime.now(timezone.utc))
            event = {'poll_number':number, 'status':'SOURCE_UNAVAILABLE',
                     'observed_at':observed_at, 'reason':str(exc)}
            tasks.append({'gap':'SNAPSHOT_SOURCE_UNAVAILABLE',
                          'question':'Can the local snapshot be made readable?',
                          'permitted_source':'the configured workspace snapshot file',
                          'priority_rationale':'No observations can be captured while the source is unavailable.',
                          'expected_evidence':'a readable JSON or CSV snapshot',
                          'budget':'one bounded local source check',
                          'stopping_condition':'source becomes readable or watch ends', 'evidence_ids':[]})
        else:
            digest = hashlib.sha256(raw).hexdigest()
            if digest == previous_hash:
                event = {'poll_number':number, 'status':'UNCHANGED', 'observed_at':observed_at,
                         'source_hash':digest}
            else:
                try:
                    snapshots = market_store._snapshots(raw, path.suffix)
                except (ValueError, UnicodeError) as exc:
                    # Preserve the exact invalid bytes even when parsing fails.
                    market_store._import_records(db_path, raw, [], captured_at=observed_at)
                    event = {'poll_number':number, 'status':'INVALID_SNAPSHOT',
                             'observed_at':observed_at, 'source_hash':digest, 'reason':str(exc)}
                    tasks.append({'gap':'INVALID_SNAPSHOT',
                                  'question':'Can the snapshot format be corrected at its source?',
                                  'permitted_source':'the configured workspace snapshot file',
                                  'priority_rationale':'Invalid input cannot be used as observations.',
                                  'expected_evidence':'a valid JSON or CSV snapshot',
                                  'budget':'one bounded local source check',
                                  'stopping_condition':'valid snapshot imported or watch ends',
                                  'source_hash':digest, 'evidence_ids':[]})
                else:
                    result = market_store._import_records(db_path, raw, snapshots, captured_at=observed_at)
                    status = ('QUARANTINED' if result['quarantined'] else
                              'IMPORTED' if result['inserted'] else 'DUPLICATE')
                    event = {'poll_number':number, 'status':status, 'observed_at':observed_at,
                             'source_hash':digest, 'import':result,
                             'declared_publication_times':sorted({s.get('source_published_at') or s.get('published_at')
                                 for s in snapshots if isinstance(s, dict) and isinstance(s.get('source_published_at') or s.get('published_at'), str)}),
                             'publication_time_status':'source-supplied claims, not independently verified'}
                    if result['quarantined']:
                        tasks.append({'gap':'QUARANTINED_SNAPSHOT_RECORD',
                                      'question':'Can the source identity or record be corrected with a new acquisition?',
                                      'permitted_source':'the configured workspace snapshot file',
                                      'priority_rationale':'Ambiguous or conflicting source records cannot be used.',
                                      'expected_evidence':'a validated snapshot with a distinct acquisition identity',
                                      'budget':'one bounded local source check',
                                      'stopping_condition':'corrected snapshot imported or watch ends',
                                      'source_hash':digest, 'evidence_ids':[]})
                previous_hash = digest
        events.append(event)
        if on_poll is not None:
            on_poll(dict(event))
        if number < iterations:
            sleeper(interval_seconds)
    return {'watch_id':str(uuid.uuid4()), 'source_path':str(path),
            'actual_run_time':market_store.utc(datetime.now(timezone.utc)),
            'clock_mode':'operational', 'watch_version':VERSION,
            'iterations_requested':iterations, 'iterations_completed':len(events),
            'interval_seconds':interval_seconds, 'events':events, 'research_tasks':tasks,
            'stop_reason':'ITERATION_LIMIT'}
