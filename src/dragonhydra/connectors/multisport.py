"""Public historical hockey/cricket downloads; no live-feed or odds claims.

MoneyPuck's published team-game CSV is transferred with standard HTTP gzip.
Cricsheet archives are parsed in memory and never extracted to the filesystem.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import re
import stat
import zipfile
import zlib

from .core import ConnectorError

MONEYPUCK_URL = 'https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_teams.csv'
CRICSHEET_DATASETS = {
    'blz': "Women's T20 Blaze", 'cec': 'Charlotte Edwards Cup',
    'frb': 'FairBreak Invitational Tournament',
}
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBERS = 1000
MAX_MEMBER_BYTES = 4 * 1024 * 1024
SPECS = {
    'moneypuck': {
        'capabilities': ['matches', 'historical_results', 'team_statistics'],
        'defaults': {'season': 2025, 'season_type': 'all'},
        'min_interval_seconds': 86400, 'live': False,
        'documentation_url': 'https://moneypuck.com/data.htm',
    },
    'cricsheet': {
        'capabilities': ['matches', 'historical_results', 'innings_statistics', 'match_participants'],
        'defaults': {'dataset': 'blz'}, 'min_interval_seconds': 3600, 'live': False,
        'documentation_url': 'https://cricsheet.org/downloads/',
    },
}


def _fail(code, message):
    raise ConnectorError(code, message)


def validate_config(provider_id, config):
    if not isinstance(provider_id, str) or provider_id not in SPECS:
        _fail('UNSUPPORTED_PROVIDER', 'This adapter supports MoneyPuck and Cricsheet only.')
    if not isinstance(config, dict):
        _fail('INVALID_CONFIG', 'Connection configuration must be an object.')
    allowed = set(SPECS[provider_id]['defaults'])
    if set(config) - allowed:
        _fail('INVALID_CONFIG', 'Only documented dataset selectors are accepted; custom URLs are not allowed.')
    result = {**SPECS[provider_id]['defaults'], **config}
    if provider_id == 'moneypuck':
        value = result['season']
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d{4}', str(value)):
            _fail('INVALID_CONFIG', 'MoneyPuck season must be its four-digit starting year.')
        result['season'] = int(value)
        if (not 2008 <= result['season'] <= 2100 or not isinstance(result['season_type'], str)
                or result['season_type'] not in ('all', 'regular', 'playoffs')):
            _fail('INVALID_CONFIG', 'Select a supported starting year and all, regular or playoffs season type.')
    elif not isinstance(result['dataset'], str) or result['dataset'] not in CRICSHEET_DATASETS:
        _fail('INVALID_CONFIG', 'Select a published bounded Cricsheet dataset: blz, cec or frb.')
    return result


def _nonnegative_integer(value, *, required=False):
    if value is None or value == '':
        if required:
            _fail('SCHEMA_MISMATCH', 'A required source count is missing.')
        return None
    if isinstance(value, bool):
        _fail('SCHEMA_MISMATCH', 'A source count must be a nonnegative integer.')
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > 1_000_000_000 or number != number.to_integral_value():
            raise InvalidOperation
        return int(number)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        _fail('SCHEMA_MISMATCH', 'A source count must be a nonnegative integer.')


def _source_number(value):
    if value is None or value == '':
        return None
    try:
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError):
        _fail('SCHEMA_MISMATCH', 'A reported source statistic is not a finite nonnegative number.')


def _date(value, compact=False):
    if not isinstance(value, str):
        _fail('SCHEMA_MISMATCH', 'The source match date is missing or invalid.')
    if compact and re.fullmatch(r'\d{8}', value):
        value = f'{value[:4]}-{value[4:6]}-{value[6:]}'
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        _fail('SCHEMA_MISMATCH', 'The source match date must have explicit day precision.')
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        _fail('SCHEMA_MISMATCH', 'The source match date is not a calendar date.')


def _csv_body(document):
    body = document.body
    if len(body) > MAX_DOWNLOAD_BYTES:
        _fail('DOWNLOAD_LIMIT', 'MoneyPuck download exceeds the bounded compressed-transfer limit.')
    if body.startswith(b'\x1f\x8b'):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                body = stream.read(MAX_CSV_BYTES + 1)
        except (OSError, EOFError, zlib.error):
            _fail('INVALID_CSV', 'The MoneyPuck gzip transfer is invalid or incomplete; original bytes were retained.')
    if len(body) > MAX_CSV_BYTES:
        _fail('DECOMPRESSION_LIMIT', 'MoneyPuck decoded CSV exceeds the 128 MiB safety limit.')
    if body.lstrip().lower().startswith((b'<html', b'<!doctype html')):
        _fail('UNEXPECTED_HTML', 'The source returned an HTML page instead of the team-game CSV.')
    try:
        return body.decode('utf-8-sig')
    except UnicodeError:
        _fail('INVALID_CSV', 'The MoneyPuck CSV is not valid UTF-8.')


def _team(row):
    value = row.get('playerTeam')
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9.]{2,5}', value):
        _fail('SCHEMA_MISMATCH', 'A MoneyPuck native team identity is invalid.')
    return value


def _hockey_stats(row):
    fields = ('xGoalsFor', 'xGoalsAgainst', 'shotsOnGoalFor', 'shotsOnGoalAgainst',
              'shotAttemptsFor', 'shotAttemptsAgainst', 'iceTime', 'penaltiesFor', 'penaltiesAgainst')
    return {key: _source_number(row.get(key)) for key in fields if row.get(key) not in (None, '')}


def _agree(left, right):
    if left is not None and right is not None and left != right:
        _fail('INCONSISTENT_SCORE', 'The two source team rows disagree on the same game score.')
    return left if left is not None else right


def parse_moneypuck(document, config, check=lambda: None):
    config = validate_config('moneypuck', config)
    check()
    reader = csv.DictReader(io.StringIO(_csv_body(document), newline=''))
    required = {'season', 'gameId', 'playerTeam', 'opposingTeam', 'home_or_away',
                'gameDate', 'situation', 'goalsFor', 'goalsAgainst', 'playoffGame'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames) or len(reader.fieldnames) != len(set(reader.fieldnames)):
        _fail('SCHEMA_MISMATCH', 'The MoneyPuck team-game CSV is missing documented columns or has duplicate headers.')
    games = {}
    try:
        for index, row in enumerate(reader):
            if index % 512 == 0:
                check()
            if None in row or any(value is None for value in row.values()):
                _fail('SCHEMA_MISMATCH', 'A MoneyPuck CSV record does not match its header.')
            if row['season'] != str(config['season']) or row['situation'].strip().lower() != 'all':
                continue
            playoff = _nonnegative_integer(row['playoffGame'], required=True)
            if playoff not in (0, 1):
                _fail('SCHEMA_MISMATCH', 'The MoneyPuck playoff indicator is invalid.')
            if config['season_type'] == 'regular' and playoff or config['season_type'] == 'playoffs' and not playoff:
                continue
            game_id = row['gameId']
            if not re.fullmatch(r'\d{10}', game_id):
                _fail('SCHEMA_MISMATCH', 'A MoneyPuck native game identity is invalid.')
            side = row['home_or_away'].upper()
            if side not in ('HOME', 'AWAY'):
                _fail('AMBIGUOUS_IDENTITY', 'The hockey source does not explicitly identify home and away.')
            team = _team(row)
            opponent = row['opposingTeam']
            if not re.fullmatch(r'[A-Z0-9.]{2,5}', opponent) or team == opponent:
                _fail('AMBIGUOUS_IDENTITY', 'The hockey source opponent identity is missing or ambiguous.')
            group = games.setdefault(game_id, {})
            if side in group and group[side] != row:
                _fail('AMBIGUOUS_IDENTITY', 'Conflicting source rows share a game and participant role.')
            group[side] = row
    except csv.Error:
        _fail('INVALID_CSV', 'The MoneyPuck CSV is malformed; exact transfer bytes were retained.')
    result = []
    for game_id, group in sorted(games.items()):
        check()
        home, away = group.get('HOME'), group.get('AWAY')
        row = home if home is not None else away
        event_date = _date(row['gameDate'], compact=True)
        if home is not None and away is not None:
            if (_team(home) != away['opposingTeam'] or _team(away) != home['opposingTeam']
                    or home['gameDate'] != away['gameDate'] or home['playoffGame'] != away['playoffGame']):
                _fail('AMBIGUOUS_IDENTITY', 'Paired hockey rows do not identify the same event, date and participants.')
        home_team = _team(home) if home is not None else away['opposingTeam']
        away_team = _team(away) if away is not None else home['opposingTeam']
        home_goals = _agree(_nonnegative_integer(home['goalsFor']) if home else None,
                            _nonnegative_integer(away['goalsAgainst']) if away else None)
        away_goals = _agree(_nonnegative_integer(away['goalsFor']) if away else None,
                            _nonnegative_integer(home['goalsAgainst']) if home else None)
        result.append({'source_record_id': game_id, 'sport': 'ice_hockey', 'competition': 'NHL',
            'season': f"{config['season']}/{config['season'] + 1}", 'home': home_team, 'away': away_team,
            'event_date': event_date, 'kickoff_utc': None, 'source_local_time': None,
            'status': 'historical_result', 'score_home': home_goals, 'score_away': away_goals,
            'statistics': {side.lower(): _hockey_stats(native) for side, native in group.items()},
            'attributes': {'attribution': 'MoneyPuck.com', 'source_url': document.url,
                'paired_team_rows': len(group) == 2, 'participant_id_namespace': 'moneypuck_team_code',
                'situation': 'all', 'playoff_game': bool(int(row['playoffGame'])),
                'score_scope': 'reported_goals_all_situations; shootout_deciding_goal_treatment_not_supplied',
                'betting_settlement_record': False, 'time_precision': 'date',
                'transport_gzip': document.body.startswith(b'\x1f\x8b')},
            'odds': [], 'source_document_sha256': document.sha256,
            'original': {'team_rows': group}})
    return result


def _safe_members(archive):
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBERS or sum(item.file_size for item in members) > MAX_ZIP_BYTES:
        _fail('ARCHIVE_LIMIT', 'The Cricsheet archive exceeds member or uncompressed-size limits.')
    seen = set()
    for member in members:
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if (not member.filename or path.is_absolute() or len(path.parts) != 1 or '..' in path.parts
                or '\\' in member.filename or ':' in member.filename or '\x00' in member.filename
                or stat.S_ISLNK(mode) or member.flag_bits & 1 or member.filename in seen
                or member.file_size > MAX_MEMBER_BYTES
                or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            _fail('ARCHIVE_UNSAFE', 'The Cricsheet archive has an unsafe, duplicate, encrypted or oversized member.')
        if member.filename not in ('README.txt', 'LICENSE.txt') and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.json', member.filename):
            _fail('ARCHIVE_UNSAFE', 'The Cricsheet archive contains an unrecognized member path.')
        seen.add(member.filename)
    return members


def _innings_summaries(innings, teams, check):
    if not isinstance(innings, list) or len(innings) > 20:
        _fail('SCHEMA_MISMATCH', 'Cricsheet innings must be a bounded array.')
    summaries = []
    for number, item in enumerate(innings, 1):
        check()
        if not isinstance(item, dict) or item.get('team') not in teams or not isinstance(item.get('overs', []), list):
            _fail('SCHEMA_MISMATCH', 'A Cricsheet innings has invalid participants or overs.')
        runs, deliveries, wicket_events = 0, 0, 0
        kinds = {}
        penalty = item.get('penalty_runs', {})
        if not isinstance(penalty, dict) or set(penalty) - {'pre', 'post'}:
            _fail('SCHEMA_MISMATCH', 'Cricsheet penalty runs have an unsupported shape.')
        for value in penalty.values():
            runs += _nonnegative_integer(value, required=True)
        for over in item.get('overs', []):
            check()
            if not isinstance(over, dict) or not isinstance(over.get('deliveries'), list):
                _fail('SCHEMA_MISMATCH', 'A Cricsheet over does not contain deliveries.')
            for delivery in over['deliveries']:
                if not isinstance(delivery, dict) or not isinstance(delivery.get('runs'), dict):
                    _fail('SCHEMA_MISMATCH', 'A Cricsheet delivery is missing its explicit runs.')
                runs += _nonnegative_integer(delivery['runs'].get('total'), required=True)
                deliveries += 1
                wickets = delivery.get('wickets', [])
                if not isinstance(wickets, list):
                    _fail('SCHEMA_MISMATCH', 'Cricsheet wicket events must be an array.')
                for wicket in wickets:
                    if not isinstance(wicket, dict) or not isinstance(wicket.get('kind'), str):
                        _fail('SCHEMA_MISMATCH', 'A Cricsheet wicket event is missing its kind.')
                    kind = wicket['kind']; kinds[kind] = kinds.get(kind, 0) + 1
                    wicket_events += 1
        summaries.append({'innings_number': number, 'team': item['team'], 'runs_total': runs,
            'recorded_delivery_count': deliveries, 'recorded_wicket_events': wicket_events,
            'wicket_event_kinds': kinds, 'penalty_runs': penalty,
            'super_over': item.get('super_over', False), 'declared': item.get('declared', False),
            'forfeited': item.get('forfeited', False), 'target': item.get('target')})
    return summaries


def parse_cricsheet(document, config, check=lambda: None):
    config = validate_config('cricsheet', config)
    if len(document.body) > MAX_DOWNLOAD_BYTES:
        _fail('DOWNLOAD_LIMIT', 'The Cricsheet compressed download exceeds the safety limit.')
    check()
    try:
        archive = zipfile.ZipFile(io.BytesIO(document.body))
    except zipfile.BadZipFile:
        _fail('ARCHIVE_INVALID', 'Cricsheet returned an invalid or incomplete JSON ZIP.')
    result = []
    with archive:
        members = _safe_members(archive)
        for member in sorted(members, key=lambda item: item.filename):
            check()
            if not member.filename.endswith('.json'):
                continue
            try:
                raw = archive.read(member)
            except (zipfile.BadZipFile, EOFError, zlib.error):
                _fail('ARCHIVE_INVALID', 'A Cricsheet member failed its ZIP integrity check.')
            try:
                native = json.loads(raw.decode('utf-8-sig'))
            except (UnicodeError, json.JSONDecodeError):
                _fail('INVALID_JSON', 'A retained Cricsheet match member contains invalid JSON.')
            if not isinstance(native, dict) or not isinstance(native.get('meta'), dict) or not isinstance(native.get('info'), dict):
                _fail('SCHEMA_MISMATCH', 'A Cricsheet match is missing meta or info.')
            version = native['meta'].get('data_version', '')
            if not isinstance(version, str) or not re.fullmatch(r'1\.[0-3]\.\d+', version):
                _fail('SCHEMA_VERSION_UNSUPPORTED', 'This adapter supports documented Cricsheet JSON 1.0 through 1.3.')
            revision = _nonnegative_integer(native['meta'].get('revision'), required=True)
            if not revision:
                _fail('SCHEMA_MISMATCH', 'Cricsheet source revision must be positive.')
            created_date = _date(native['meta'].get('created'))
            info = native['info']; teams = info.get('teams'); dates = info.get('dates')
            if (not isinstance(teams, list) or len(teams) != 2 or any(not isinstance(team, str) or not team.strip() for team in teams)
                    or teams[0] == teams[1] or not isinstance(dates, list) or not dates):
                _fail('AMBIGUOUS_IDENTITY', 'Cricsheet must identify two distinct participants and its actual dates.')
            parsed_dates = [_date(value) for value in dates]
            if parsed_dates != sorted(set(parsed_dates)):
                _fail('SCHEMA_MISMATCH', 'Cricsheet match dates must be unique and chronological.')
            season = info.get('season')
            if season is None:
                season = 'unknown'
            elif isinstance(season, bool) or not isinstance(season, (str, int)):
                _fail('SCHEMA_MISMATCH', 'Cricsheet season must retain its source label.')
            event = info.get('event', {})
            if not isinstance(event, dict) or not isinstance(info.get('outcome', {}), dict):
                _fail('SCHEMA_MISMATCH', 'Cricsheet event or outcome has an unsupported shape.')
            if info.get('outcome', {}).get('winner') is not None and info['outcome']['winner'] not in teams:
                _fail('AMBIGUOUS_IDENTITY', 'Cricsheet outcome names a participant outside this match.')
            competition = event.get('name', CRICSHEET_DATASETS[config['dataset']])
            if not isinstance(competition, str) or not competition.strip():
                _fail('SCHEMA_MISMATCH', 'Cricsheet competition identity is invalid.')
            summaries = _innings_summaries(native.get('innings', []), teams, check)
            result.append({'source_record_id': member.filename[:-5], 'sport': 'cricket',
                'competition': competition, 'season': str(season), 'home': teams[0], 'away': teams[1],
                'event_date': parsed_dates[0], 'kickoff_utc': None, 'source_local_time': None,
                'status': 'historical_result', 'score_home': None, 'score_away': None,
                'venue': info.get('venue'),
                'statistics': {'innings': summaries, 'outcome': info.get('outcome', {}),
                    'participants': info.get('players', {}), 'match_type': info.get('match_type'),
                    'balls_per_over': info.get('balls_per_over')},
                'attributes': {'attribution': 'Cricsheet', 'source_url': document.url,
                    'archive_member': member.filename, 'archive_member_sha256': hashlib.sha256(raw).hexdigest(),
                    'format_version': version, 'source_revision': revision,
                    'source_created_date': created_date, 'event_dates': parsed_dates,
                    'participant_order': 'source_order', 'home_away_designation_provided': False,
                    'gender': info.get('gender'), 'team_type': info.get('team_type'),
                    'time_precision': 'date', 'dataset': config['dataset'],
                    'score_interpretation': 'separate innings; no inferred two-number match score'},
                'odds': [], 'source_document_sha256': document.sha256, 'original': native})
    if not result:
        _fail('NO_RECORDS', 'The Cricsheet ZIP contains no match JSON records.')
    return result


def fetch(provider_id, config, secret, transport, check=lambda: None):
    selected = validate_config(provider_id, config)
    check()
    if provider_id == 'moneypuck':
        document = transport.get(MONEYPUCK_URL, headers={'Accept-Encoding': 'gzip'})
        check()
        return parse_moneypuck(document, selected, check)
    document = transport.get(f"https://cricsheet.org/downloads/{selected['dataset']}_json.zip")
    check()
    return parse_cricsheet(document, selected, check)
