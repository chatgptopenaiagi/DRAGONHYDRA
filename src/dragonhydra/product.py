"""Application services for the product UI; existing research modules remain owners.

This increment deliberately uses an explicit SQLite backend in a separate product
state directory. It never changes authority or copies the existing research DB.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from . import public_results, market_store
from .cognition import models
from .build_meta import VERSION

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
API = '/dragon/api/v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def identity(*parts):
    return hashlib.sha256(json.dumps(['v1', *parts], ensure_ascii=False).encode()).hexdigest()


class Product:
    def __init__(self, state: Path, source_root: Path = ROOT):
        self.state = Path(state).resolve()
        self.source_root = Path(source_root).resolve()
        packaged = Path(__file__).parent / 'resources'
        if self.source_root == ROOT and (packaged / 'data' / 'raw').is_dir():
            self.source_root = packaged
        self.state.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state / 'core.sqlite3'
        with closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            public_results._schema(db)
            db.commit()
        self.exports = self.state / 'exports'
        self.exports.mkdir(exist_ok=True)
        from .connectors.store import Store
        self.connector_store = Store(self)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def rows(self):
        with closing(self.connect()) as db:
            rows = public_results.latest(db, now())
        for item in self.connector_store.rows(sport='football'):
            record = item['record']
            home, away = record.get('score_home'), record.get('score_away')
            result = record['status'] == 'historical_result' and home is not None and away is not None
            rows.append({'source_id': item['provider'], 'fixture_key': item['source_record_id'],
                'competition': record['competition']+' '+str(record.get('season') or ''),
                'home': record['home'], 'away': record['away'], 'event_date': record['event_date'],
                'event_at_utc': record.get('kickoff_utc'), 'source_local_time': record.get('source_local_time'),
                'home_goals': home, 'away_goals': away, 'outcome': ('H' if home > away else 'D' if home == away else 'A') if result else None,
                'result_state': 'available' if result else 'unavailable', 'source_url': item['original_url'],
                'source_hash': item['raw_sha256'], 'evidence_id': item['id'], 'received_at': item['received_at'],
                'usable_at': item['usable_at'], '_connector': record, 'raw_reference': item['raw_reference']})
        return rows

    def match_id(self, row):
        return identity('fixture', row['source_id'], row['fixture_key'])

    def competition_id(self, row):
        return identity('competition-season', row['source_id'], row['competition'])

    def team_id(self, row, name):
        # Source-local names; no unsupported cross-provider or cross-season join.
        return identity('participant', row['source_id'], name)

    def present(self, row):
        season = re.search(r'20\d{2}/\d{2}', row['competition'])
        record = row.get('_connector', {})
        status = {'historical_result': 'finished'}.get(record.get('status'), record.get('status')) or ('finished' if row['result_state'] == 'available' else 'scheduled')
        return {'id': self.match_id(row), 'version': row['evidence_id'],
                'identity_version': 1, 'competition_id': self.competition_id(row),
                'competition': row['competition'], 'season': record.get('season') or (season.group() if season else None),
                'home': {'id': self.team_id(row, row['home']), 'name': row['home']},
                'away': {'id': self.team_id(row, row['away']), 'name': row['away']},
                'event_date': row['event_date'], 'kickoff_utc': row['event_at_utc'],
                'time_precision': 'instant' if row['event_at_utc'] else 'local_time' if row['source_local_time'] else 'date', 'source_local_time': row['source_local_time'],
                'status': status, 'record_kind': record.get('status', 'historical_result' if row['outcome'] else 'scheduled'),
                'sport': 'football',
                'score_scope': record.get('attributes', {}).get('score_scope', 'Retained source score; settlement scope must be checked separately.'),
                'score': {'home': row['home_goals'], 'away': row['away_goals']} if row['home_goals'] is not None and row['away_goals'] is not None else None,
                'source_id': row['source_id'], 'source_url': row['source_url'],
                'evidence_id': row['evidence_id'], 'received_at': row['received_at'],
                'usable_at': row['usable_at'], 'data_state': 'Live' if status == 'live' else 'Scheduled' if status == 'scheduled' else 'Synthetic demo' if status == 'synthetic' else 'Historical',
                'capabilities': {'events': False, 'lineups': False, 'statistics': bool(record.get('statistics')), 'odds': bool(record.get('odds'))}}

    def find(self, match_id):
        for row in self.rows():
            if self.match_id(row) == match_id:
                return row
        raise LookupError('MATCH_NOT_FOUND')

    def matches(self, *, date=None, status=None, competition=None, provider=None, search='', limit=50, offset=0):
        rows = [self.present(r) for r in self.rows()]
        rows = [r for r in rows if (not date or r['event_date'] == date)
                and (not status or r['status'] == status)
                and (not competition or r['competition_id'] == competition)
                and (not provider or r['source_id'] == provider)
                and (not search or search.casefold() in (r['home']['name']+' '+r['away']['name']).casefold())]
        rows.sort(key=lambda r: (r['event_date'], r['id']), reverse=True)
        return {'items': rows[offset:offset+limit], 'total': len(rows), 'limit': limit, 'offset': offset,
                'as_of': now(), 'timestamp_semantics': 'UTC when evidenced; date-only and source-local times remain explicitly imprecise. UTC receipt clocks.'}

    def competitions(self):
        result = {}
        for row in self.rows():
            m = self.present(row)
            result[m['competition_id']] = {'id': m['competition_id'], 'name': m['competition'], 'season': m['season']}
        return {'items': sorted(result.values(), key=lambda r: r['name'])}

    def team(self, team_id):
        matches, name, form = [], None, []
        for row in self.rows():
            side = next((s for s in ('home', 'away') if self.team_id(row, row[s]) == team_id), None)
            if side is None:
                continue
            name = row[side]
            matches.append(self.present(row))
            if row['outcome']:
                gf = row[side+'_goals']
                ga = row[('away' if side == 'home' else 'home')+'_goals']
                form.append({'match_id': self.match_id(row), 'date': row['event_date'],
                    'opponent': row['away' if side == 'home' else 'home'], 'result': 'W' if gf > ga else 'D' if gf == ga else 'L',
                    'goals_for': gf, 'goals_against': ga})
        if name is None:
            raise LookupError('TEAM_NOT_FOUND')
        return {'id': team_id, 'name': name,
                'matches': sorted(matches, key=lambda r: r['event_date'], reverse=True),
                'form': sorted(form, key=lambda r: r['date'], reverse=True)[:10],
                'unknowns': ['Squad, injuries, suspensions and confirmed lineups are not supplied by this connector.',
                             'Team identity is scoped to the source dataset; cross-source aliases have not been approved.']}

    def standings(self, competition_id):
        rows = [r for r in self.rows() if self.competition_id(r) == competition_id]
        if not rows:
            raise LookupError('COMPETITION_NOT_FOUND')
        stages = {r.get('_connector', {}).get('attributes', {}).get('competition_stage', {}).get('name')
                  for r in rows if isinstance(r.get('_connector', {}).get('attributes', {}).get('competition_stage'), dict)}
        if stages-{'Regular Season', None}:
            return {'competition': rows[0]['competition'], 'season': self.present(rows[0])['season'],
                    'official': False, 'available': False, 'label': 'Tournament stages; a single league table is not applicable',
                    'items': [], 'source_id': rows[0]['source_id'], 'as_of': now(), 'stages': sorted(s for s in stages if s),
                    'limitations': ['Group membership, qualification and tie-break rules are not normalized. No combined points table or invented bracket is produced.']}
        table = {}
        for row in rows:
            for name in (row['home'], row['away']):
                table.setdefault(name, dict(team_id=self.team_id(row, name), team=name, played=0,
                    won=0, drawn=0, lost=0, goals_for=0, goals_against=0, points=0))
            if not row['outcome']:
                continue
            for side, other in (('home', 'away'), ('away', 'home')):
                team = table[row[side]]
                gf, ga = row[side+'_goals'], row[other+'_goals']
                team['played'] += 1
                team['goals_for'] += gf
                team['goals_against'] += ga
                key = 'won' if gf > ga else 'drawn' if gf == ga else 'lost'
                team[key] += 1
                team['points'] += 3 if gf > ga else 1 if gf == ga else 0
        return {'competition': rows[0]['competition'], 'season': self.present(rows[0])['season'],
                'official': False, 'label': 'Calculated from retained full-time results',
                'items': sorted(table.values(), key=lambda x: (-x['points'], -(x['goals_for']-x['goals_against']), -x['goals_for'], x['team'])),
                'source_id': rows[0]['source_id'], 'as_of': now(),
                'limitations': ['Three points per win; deductions and competition tie-break rules are not supplied.',
                               'This is a descriptive table, not an official provider standing.']}

    def predictions(self, match_id):
        target = self.find(match_id)
        if target['outcome']:
            return {'available': False, 'reason': 'No prospective forecast was retained for this finished match.',
                    'models': [], 'ensemble': None, 'expected_goals': None, 'cutoff': now(),
                    'interpretation': 'Later results are never presented as a pre-match prediction.'}
        if target.get('_connector'):
            return {'available': False, 'reason': 'This source has no evaluated, evidence-bound forecast cohort yet. Retained results, statistics and odds remain available.',
                    'models': [], 'ensemble': None, 'expected_goals': None, 'cutoff': now()}
        cutoff = now()
        try:
            result = models.forecast(self.rows(), target, cutoff, lambda h: market_store.raw_source(self.db_path, h))
        except ValueError as exc:
            return {'available': False, 'reason': str(exc), 'models': [], 'ensemble': None,
                    'expected_goals': None, 'cutoff': cutoff, 'interpretation': 'Forecast abstained.'}
        return {'available': not result['abstained'], 'reason': None,
                'models': [{'id': name, 'available': value['available'],
                    'probabilities': {k: v['value'] for k, v in value.get('probabilities', {}).items()},
                    'reason': value.get('reason')} for name, value in result['models'].items()],
                'ensemble': {k: v['value'] for k, v in result['ensemble']['probabilities'].items()} if result['ensemble'] else None,
                'expected_goals': result['models']['poisson_goals'].get('expected_goals'),
                'scorelines': result['models']['poisson_goals'].get('scorelines', []),
                'cutoff': cutoff, 'interpretation': 'Current uncalibrated statistical forecast; shared evidence, equal weights absent eligible evaluation.',
                'evidence_ids': [r['evidence_id'] for r in result['training_manifest']],
                'model_version': result['model_version'], 'training_count': result['training_count']}

    def explanation(self, match_id):
        row = self.find(match_id)
        score = f"{row['home_goals']}–{row['away_goals']}" if row['outcome'] else 'result not supplied'
        return {'kind': 'deterministic', 'summary': f"{row['home']} vs {row['away']}: {score}.",
                'observations': [f"Source: {row['competition']}; source event date {row['event_date']}.",
                                 f"Evidence became usable locally at {row['usable_at']}.",
                                 'No cross-provider odds mapping has been approved for this event.'],
                'evidence': [{'id': row['evidence_id'], 'url': API+'/evidence/'+row['evidence_id'], 'label': 'Retained source record'}],
                'unknowns': ['Exact UTC kickoff', 'Confirmed lineups and injuries', 'Contemporaneous compatible odds',
                             'This standard explanation is deterministic; local model use requires the separate optional action.'],
                'cutoff': now(), 'input_manifest': [row['evidence_id']], 'version': 'evidence-summary/1'}

    def evidence(self, evidence_id):
        for row in public_results.get_as_of(self.db_path, now()):
            if row['evidence_id'] == evidence_id:
                return row
        return self.connector_store.evidence(evidence_id)

    def odds(self, match_id, history=False):
        row = self.find(match_id)
        record = row.get('_connector')
        if not record:
            return {'items': [], 'axis': 'capture_time', 'reason': 'No approved cross-source market mapping for this canonical event. Archive prices are kept separate.'}
        items = []
        observations = [self.connector_store.evidence(row['evidence_id'])]
        if history:
            with closing(self.connect()) as db:
                ids = db.execute('SELECT id FROM connector_observations WHERE provider=? AND source_record_id=? ORDER BY seq', (row['source_id'], row['fixture_key'])).fetchall()
            observations = [self.connector_store.evidence(r[0]) for r in ids]
        for observation in observations:
            for index, quote in enumerate(observation['record'].get('odds', [])):
                source = self.connector_store.quote_source(observation, quote, index)
                items.append({**quote, 'match_id': match_id, 'captured_at': source.get('captured_at'),
                              'source_document_sha256': quote.get('source_document_sha256'),
                              'acquisition_id': source.get('id'), 'acquisition_url': source.get('metadata_url'),
                              'source_url': source.get('original_url'), 'resolved_source_url': source.get('resolved_url'),
                              'provenance_status': source['status'], 'provenance_code': source.get('code'),
                              'evidence_id': observation['id'], 'observation_evidence_id': observation['id'],
                              'observation_received_at': observation['received_at'], 'source_id': row['source_id']})
        archival = any(q.get('archive_phase') for q in items)
        return {'items': items, 'axis': 'archive_phase' if archival else 'capture_time',
                'reason': 'Untimestamped archival opening/closing endpoints; no source-time velocity or intraday curve is implied.' if archival else 'Provider-scoped compatible markets; UTC local capture times are distinct from provider quote times.'}
