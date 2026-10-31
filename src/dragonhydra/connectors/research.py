"""Public StatsBomb and nflverse match datasets, without live-feed claims.

StatsBomb's original repository URL intentionally follows its current Hudl
redirect through the shared retaining transport. NFL game times are Eastern
according to the upstream schedules dictionary; StatsBomb's naive times are
preserved without inventing a timezone. Exact raw rows remain in ``original``.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
import io
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .core import ConnectorError


STATSBOMB_BASE = 'https://github.com/statsbomb/open-data/raw/refs/heads/master/data/'
NFL_SCHEDULES = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
NFL_DICTIONARY = 'https://nflreadr.nflverse.com/articles/dictionary_schedules.html'
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
SPECS = {
    'statsbomb': {
        'capabilities': ['competition_catalog', 'fixtures', 'results', 'team_metadata'],
        'defaults': {'competition_id': 43, 'season_id': 106},
        'min_interval_seconds': 3600, 'live': False,
        'documentation_url': 'https://github.com/hudl/open-data',
    },
    'nflverse': {
        'capabilities': ['fixtures', 'results', 'american_football_context'],
        'defaults': {'seasons': [2025]},
        'min_interval_seconds': 3600, 'live': False,
        'documentation_url': 'https://nflreadr.nflverse.com/reference/load_schedules.html',
    },
}


def _error(code='SCHEMA_MISMATCH', message='The public dataset does not match the expected schema; exact bytes were retained.'):
    raise ConnectorError(code, message)


def _integer(value, *, minimum=0, maximum=1_000_000_000, optional=False, config=False):
    if value is None or (isinstance(value, str) and value.strip() in ('', 'NA', 'NaN')):
        if optional:
            return None
        _error('INVALID_CONFIG' if config else 'SCHEMA_MISMATCH', 'A required numeric configuration value is missing.' if config else 'A required dataset number is missing.')
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'-?\d+', str(value).strip()):
        _error('INVALID_CONFIG' if config else 'SCHEMA_MISMATCH', 'Use bounded integer configuration values.' if config else 'A dataset integer is invalid.')
    number = int(value)
    if not minimum <= number <= maximum:
        _error('INVALID_CONFIG' if config else 'SCHEMA_MISMATCH', 'The requested integer is outside its supported range.' if config else 'A dataset integer is outside its supported range.')
    return number


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 300 or any(ord(c) < 32 for c in value):
        _error()
    return value.strip()


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        _error()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        _error()


def _clock(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?', value):
        _error()
    try:
        return time.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        _error()


def validate_config(provider, config):
    if not isinstance(config, dict):
        _error('INVALID_CONFIG', 'Provider configuration must be an object.')
    if provider == 'statsbomb':
        if set(config) - {'competition_id', 'season_id'}:
            _error('INVALID_CONFIG', 'StatsBomb accepts only competition_id and season_id; custom URLs are not supported.')
        return {key: _integer(config.get(key, default), minimum=1, config=True)
                for key, default in SPECS[provider]['defaults'].items()}
    if provider == 'nflverse':
        if set(config) - {'seasons', 'season', 'start_season', 'end_season'}:
            _error('INVALID_CONFIG', 'nflverse accepts only a bounded season selection; custom URLs are not supported.')
        modes = sum((bool({'seasons'} & config.keys()), bool({'season'} & config.keys()),
                     bool({'start_season', 'end_season'} & config.keys())))
        if modes > 1:
            _error('INVALID_CONFIG', 'Choose seasons, one season, or a start/end season range.')
        if 'season' in config:
            values = [config['season']]
        elif 'start_season' in config or 'end_season' in config:
            if not {'start_season', 'end_season'} <= config.keys():
                _error('INVALID_CONFIG', 'Both start_season and end_season are required.')
            first = _integer(config['start_season'], minimum=1999, maximum=2100, config=True)
            last = _integer(config['end_season'], minimum=1999, maximum=2100, config=True)
            if last < first or last - first >= 5:
                _error('INVALID_CONFIG', 'Select between one and five consecutive NFL seasons.')
            values = list(range(first, last + 1))
        else:
            values = config.get('seasons', SPECS[provider]['defaults']['seasons'])
        if not isinstance(values, list) or not 1 <= len(values) <= 5:
            _error('INVALID_CONFIG', 'Select between one and five NFL seasons.')
        return {'seasons': sorted({_integer(v, minimum=1999, maximum=2100, config=True) for v in values})}
    _error('UNKNOWN_PROVIDER', 'This adapter does not implement the requested provider.')


def _get(transport, url, check):
    check()
    doc = transport.get(url)
    check()
    if len(doc.body) > MAX_DOCUMENT_BYTES:
        _error('DATA_LIMIT', 'The research dataset exceeds the bounded adapter size.')
    return doc


def _rows(doc, limit):
    value = doc.json()
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(row, dict) for row in value):
        _error()
    return value


def _deduplicate(records):
    unique = {}
    for record in records:
        key = record['source_record_id']
        if key in unique:
            if unique[key]['original'] != record['original']:
                _error('DUPLICATE_CONFLICT', 'Conflicting rows share a provider record ID; this batch needs review.')
        else:
            unique[key] = record
    return list(unique.values())


def _statsbomb(config, transport, check):
    catalog_doc = _get(transport, STATSBOMB_BASE + 'competitions.json', check)
    catalog = _rows(catalog_doc, 5000)
    selected = [row for row in catalog
                if row.get('competition_id') == config['competition_id'] and row.get('season_id') == config['season_id']]
    if not selected:
        _error('COVERAGE_UNAVAILABLE', 'The selected StatsBomb competition and season are not in the public catalog.')
    if any(row != selected[0] for row in selected[1:]):
        _error('DUPLICATE_CONFLICT', 'The public catalog contains conflicting competition-season entries.')
    competition = _name(selected[0].get('competition_name'))
    season = _name(selected[0].get('season_name'))
    matches_doc = _get(transport, STATSBOMB_BASE + f"matches/{config['competition_id']}/{config['season_id']}.json", check)
    results = []
    for index, row in enumerate(_rows(matches_doc, 5000)):
        if index % 100 == 0:
            check()
        nested_competition, nested_season = row.get('competition'), row.get('season')
        home, away = row.get('home_team'), row.get('away_team')
        if not all(isinstance(v, dict) for v in (nested_competition, nested_season, home, away)):
            _error()
        if nested_competition.get('competition_id') != config['competition_id'] or nested_season.get('season_id') != config['season_id']:
            _error('IDENTITY_MISMATCH', 'A match belongs to a different competition or season than the requested public file.')
        event_date = _date(row.get('match_date'))
        local_clock = _clock(row.get('kick_off'))
        kickoff = None
        if local_clock and local_clock.tzinfo is not None:
            kickoff = datetime.combine(date.fromisoformat(event_date), local_clock).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        home_score = _integer(row.get('home_score'), optional=True, maximum=1000)
        away_score = _integer(row.get('away_score'), optional=True, maximum=1000)
        if (home_score is None) != (away_score is None):
            _error('INCOMPLETE_SCORE', 'The dataset supplies only one participant score; no zero was inferred.')
        stadium = row.get('stadium') or {}
        if not isinstance(stadium, dict):
            _error()
        results.append({
            'source_record_id': str(_integer(row.get('match_id'), minimum=1)), 'sport': 'football',
            'competition': competition, 'season': season,
            'home': _name(home.get('home_team_name')), 'away': _name(away.get('away_team_name')),
            'event_date': event_date, 'kickoff_utc': kickoff, 'source_local_time': row.get('kick_off') or None,
            'status': 'historical_result' if home_score is not None else 'scheduled',
            'score_home': home_score, 'score_away': away_score, 'venue': stadium.get('name'),
            'statistics': {}, 'odds': [], 'source_document_sha256': matches_doc.sha256, 'original': row,
            'attributes': {
                'competition_id': config['competition_id'], 'season_id': config['season_id'],
                'home_team_id': home.get('home_team_id'), 'away_team_id': away.get('away_team_id'),
                'competition_stage': row.get('competition_stage'), 'match_week': row.get('match_week'),
                'metadata': row.get('metadata'), 'source_match_status': row.get('match_status'),
                'time_precision': 'source_offset' if kickoff else ('local_time_timezone_unspecified' if local_clock else 'date_only'),
                'score_scope': 'Provider match score; regulation, extra-time and shootout breakdown is not inferred.',
                'catalog_sha256': catalog_doc.sha256, 'catalog_url': catalog_doc.url,
                'catalog_resolved_url': catalog_doc.resolved_url, 'source_url': matches_doc.url,
                'resolved_source_url': matches_doc.resolved_url, 'captured_at': matches_doc.captured_at,
                'original_repository_url': 'https://github.com/statsbomb/open-data',
                'resolved_repository_url': 'https://github.com/hudl/open-data',
                'limitations': ['Match metadata only; per-match events, lineups and 360 payloads are not fetched by this adapter.',
                                'Source update strings are retained in original, not interpreted as historical availability.'],
            },
        })
    if not results:
        _error('NO_DATA', 'No matches are available in the selected public competition-season file.')
    check()
    return _deduplicate(results)


def _nfl_kickoff(event_date, value):
    clock = _clock(value)
    if not clock:
        return None, 'date_only'
    if clock.tzinfo is not None:
        _error('SCHEMA_MISMATCH', 'The documented Eastern NFL time column unexpectedly contains an offset.')
    try:
        eastern = ZoneInfo('America/New_York')
    except ZoneInfoNotFoundError:
        # The optional server runtime normally supplies tzdata. Browsing remains
        # possible on a lightweight runtime without inventing UTC conversion.
        return None, 'documented_eastern_timezone_database_unavailable'
    naive = datetime.combine(date.fromisoformat(event_date), clock)
    instants = set()
    for fold in (0, 1):
        instant = naive.replace(tzinfo=eastern, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(eastern).replace(tzinfo=None) == naive:
            instants.add(instant)
    if len(instants) != 1:
        return None, 'ambiguous_eastern_time' if instants else 'nonexistent_eastern_time'
    return instants.pop().isoformat().replace('+00:00', 'Z'), 'documented_eastern_time'


def _nflverse(config, transport, check):
    document = _get(transport, NFL_SCHEDULES, check)
    try:
        reader = csv.DictReader(io.StringIO(document.text(), newline=''), strict=True)
        required = {'game_id', 'season', 'game_type', 'week', 'gameday', 'gametime', 'home_team', 'away_team', 'home_score', 'away_score'}
        fields = reader.fieldnames or []
        if not required <= set(fields) or len(fields) != len(set(fields)):
            _error('SCHEMA_MISMATCH', 'The NFL schedule CSV is missing required or has duplicate columns.')
        records = []
        for index, row in enumerate(reader):
            if index > 100_000:
                _error('DATA_LIMIT', 'The NFL schedule contains too many rows for one bounded acquisition.')
            if index % 100 == 0:
                check()
            if None in row or any(value is None for value in row.values()):
                _error('SCHEMA_MISMATCH', 'An NFL schedule row is truncated or has unexpected columns.')
            season = _integer(row['season'], minimum=1999, maximum=2100)
            if season not in config['seasons']:
                continue
            identifier = row['game_id']
            if not re.fullmatch(r'\d{4}_\d{2,3}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4}', identifier):
                _error()
            home, away = _name(row['home_team']), _name(row['away_team'])
            if identifier.split('_')[0] != str(season) or identifier.split('_')[-2:] != [away, home]:
                _error('IDENTITY_MISMATCH', 'NFL game identity conflicts with its season or participants.')
            event_date = _date(row['gameday'])
            kickoff, precision = _nfl_kickoff(event_date, row['gametime'])
            home_score = _integer(row['home_score'], optional=True, maximum=1000)
            away_score = _integer(row['away_score'], optional=True, maximum=1000)
            if (home_score is None) != (away_score is None):
                _error('INCOMPLETE_SCORE', 'The NFL schedule supplies one score only; missing points were not replaced with zero.')
            statistics = {}
            for key in ('home_rest', 'away_rest', 'result', 'total', 'overtime', 'temp', 'wind'):
                if row.get(key, '').strip() not in ('', 'NA', 'NaN'):
                    statistics[key] = _integer(row[key], minimum=-1000 if key in ('result', 'temp') else 0, maximum=1000)
            archival = {key: row[key] for key in ('away_moneyline', 'home_moneyline', 'spread_line', 'away_spread_odds',
                        'home_spread_odds', 'total_line', 'under_odds', 'over_odds') if row.get(key, '').strip() not in ('', 'NA', 'NaN')}
            records.append({
                'source_record_id': identifier, 'sport': 'american_football',
                'competition': 'National Football League', 'season': str(season), 'home': home, 'away': away,
                'event_date': event_date, 'kickoff_utc': kickoff, 'source_local_time': row['gametime'] or None,
                'status': 'historical_result' if home_score is not None else 'scheduled',
                'score_home': home_score, 'score_away': away_score, 'venue': row.get('stadium') or None,
                'statistics': statistics, 'odds': [], 'source_document_sha256': document.sha256, 'original': row,
                'attributes': {
                    'game_type': _name(row['game_type']), 'week': _integer(row['week'], minimum=0, maximum=30),
                    'source_timezone': 'America/New_York', 'timezone_reference': NFL_DICTIONARY, 'time_precision': precision,
                    'score_units': 'points', 'home_designation': row.get('location') or None,
                    'source_url': document.url, 'resolved_source_url': document.resolved_url, 'captured_at': document.captured_at,
                    'archival_betting_columns': archival,
                    'limitations': ['Published schedule snapshot; not a live score feed.',
                                    'Betting columns lack bookmaker/quote-time/settlement identity and are not normalized as compatible odds.'],
                    **{key: row[key] for key in ('roof', 'surface', 'home_qb_id', 'away_qb_id', 'home_qb_name', 'away_qb_name',
                                               'home_coach', 'away_coach', 'referee', 'stadium_id') if row.get(key)},
                },
            })
    except (csv.Error, UnicodeError):
        _error('SCHEMA_MISMATCH', 'The NFL schedule is not a valid CSV dataset; exact bytes were retained.')
    if not records:
        _error('COVERAGE_UNAVAILABLE', 'The public NFL schedule contains no records for the requested seasons.')
    check()
    return _deduplicate(records)


def fetch(provider_id, config, secret, transport, check):
    """Return complete bounded selections; public sources never send ``secret``."""
    selected = validate_config(provider_id, config)
    if provider_id == 'statsbomb':
        return _statsbomb(selected, transport, check)
    return _nflverse(selected, transport, check)
