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

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def rows(self):
        with closing(self.connect()) as db:
            return public_results.latest(db, now())

    def match_id(self, row):
        return identity('fixture', row['source_id'], row['fixture_key'])

    def competition_id(self, row):
        return identity('competition-season', row['source_id'], row['competition'])

    def team_id(self, row, name):
        # Source-local names; no unsupported cross-provider or cross-season join.
        return identity('participant', row['source_id'], name)

    def present(self, row):
        season = re.search(r'20\d{2}/\d{2}', row['competition'])
        return {'id': self.match_id(row), 'version': row['evidence_id'],
                'identity_version': 1, 'competition_id': self.competition_id(row),
                'competition': row['competition'], 'season': season.group() if season else None,
                'home': {'id': self.team_id(row, row['home']), 'name': row['home']},
                'away': {'id': self.team_id(row, row['away']), 'name': row['away']},
                'event_date': row['event_date'], 'kickoff_utc': row['event_at_utc'],
                'time_precision': 'date', 'source_local_time': row['source_local_time'],
                'status': 'finished' if row['result_state'] == 'available' else 'scheduled',
                'score': {'home': row['home_goals'], 'away': row['away_goals']} if row['outcome'] else None,
                'source_id': row['source_id'], 'source_url': row['source_url'],
                'evidence_id': row['evidence_id'], 'received_at': row['received_at'],
                'usable_at': row['usable_at'], 'data_state': 'Historical',
                'capabilities': {'events': False, 'lineups': False, 'statistics': False, 'odds': False}}

    def find(self, match_id):
        for row in self.rows():
            if self.match_id(row) == match_id:
                return row
        raise LookupError('MATCH_NOT_FOUND')

    def matches(self, *, date=None, status=None, competition=None, search='', limit=50, offset=0):
        rows = [self.present(r) for r in self.rows()]
        rows = [r for r in rows if (not date or r['event_date'] == date)
                and (not status or r['status'] == status)
                and (not competition or r['competition_id'] == competition)
                and (not search or search.casefold() in (r['home']['name']+' '+r['away']['name']).casefold())]
        rows.sort(key=lambda r: (r['event_date'], r['id']), reverse=True)
        return {'items': rows[offset:offset+limit], 'total': len(rows), 'limit': limit, 'offset': offset,
                'as_of': now(), 'timestamp_semantics': 'Date-only source; kickoff timezone unknown. UTC receipt clocks.'}

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
                             'Local LLM not configured; this explanation is deterministic.'],
                'cutoff': now(), 'input_manifest': [row['evidence_id']], 'version': 'evidence-summary/1'}

    def evidence(self, evidence_id):
        for row in public_results.get_as_of(self.db_path, now()):
            if row['evidence_id'] == evidence_id:
                return row
        raise LookupError('EVIDENCE_NOT_FOUND')
