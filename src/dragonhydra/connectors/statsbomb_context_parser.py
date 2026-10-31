"""Bounded native projections; never official match statistics or inference.

Consumed fields follow the retained official event v1.1 general attributes
(lines 479–695) and lineup v2.0.0 specifications. General attributes apply
only when relevant: missing team/player/relative clocks remain absent. The
lineup PDF labels team_name/player_name Integer; that conflicts with textual
names in the main spec and existing official SDK/source adapter. We accept
textual names, without deriving identity from names or inferring sports data.

Only the listed native fields are projected. Event-specific fields (including
possession/xG), lineup positions/cards and all other unknown fields stay in
the retained raw JSON. They are checked for valid finite bounded JSON, not
interpreted. Source array order and relative clocks are retained unchanged.
"""
from collections import Counter
import json
import math
from pathlib import Path
import re
from uuid import UUID

from ..cognition import memory
from . import statsbomb_context as binding


VERSION = 'statsbomb-context/1'
MAX_EVENTS = 20_000
MAX_SQUAD = 100
MAX_TYPES = 256
MAX_PAGE = 200
MAX_PROJECTION_BYTES = 768 * 1024
OPTIONAL_EVENT_FIELDS = ('team','player','period','timestamp','minute','second')
SCOPE = 'Counts of retained event rows by native team, period and event type; not official match statistics. Null count dimensions mean the source field was absent.'
ATTRIBUTION = 'StatsBomb Open Data; source squad entries and native event fields only.'


def _fail(code):
    raise ValueError('STATSBOMB_PARSER_' + code)


def _json(raw):
    if not isinstance(raw,bytes) or len(raw) > binding.MAX_DOCUMENT_BYTES:
        _fail('DOCUMENT_LIMIT')
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                _fail('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            _fail('NONFINITE_JSON')
        return result
    try:
        value = json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_float=number,
                           parse_constant=lambda _: _fail('NONFINITE_JSON'))
        pending = [(value,0)]
        while pending:
            item,depth = pending.pop()
            if depth > 64:
                _fail('JSON_DEPTH_LIMIT')
            if isinstance(item,str):
                item.encode('utf-8')
            elif isinstance(item,dict):
                for key,child in item.items():
                    key.encode('utf-8')
                    pending.append((child,depth+1))
            elif isinstance(item,list):
                pending.extend((child,depth+1) for child in item)
        return value
    except (UnicodeError,RecursionError,OverflowError):
        _fail('INVALID_JSON')
    except ValueError as exc:
        if str(exc).startswith('STATSBOMB_PARSER_'):
            raise
        _fail('INVALID_JSON')


def _int(value,minimum=1,maximum=1_000_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail('INVALID_INTEGER')
    return value


def _name(value):
    if (not isinstance(value,str) or not value or value != value.strip()
            or len(value.encode('utf-8')) > 300 or any(ord(char)<32 for char in value)):
        _fail('INVALID_NAME')
    return value


def _named(value):
    if not isinstance(value,dict) or set(value) != {'id','name'}:
        _fail('INVALID_NAMED_ID')
    return {'id':_int(value['id']),'name':_name(value['name'])}


def _parent_teams(parent):
    expected = {'match_id':3869685,'competition_id':43,'season_id':106,
                'home_team_id':779,'away_team_id':771,'event_date':'2022-12-18'}
    if not isinstance(parent,dict) or memory._canonical(parent.get('native_identity')) != memory._canonical(expected):
        _fail('PARENT_SELECTION_MISMATCH')
    record = parent.get('normalized_record')
    if not isinstance(record,dict):
        _fail('PARENT_SELECTION_MISMATCH')
    return {779:_name(record.get('home')),771:_name(record.get('away'))}


def _squads(rows,teams):
    if not isinstance(rows,list) or len(rows) != 2:
        _fail('TWO_SQUADS_REQUIRED')
    result,roster,seen_teams = [],{},set()
    for row in rows:
        if not isinstance(row,dict):
            _fail('INVALID_SQUAD')
        team = _int(row.get('team_id'))
        if team not in teams or team in seen_teams or row.get('team_name') != teams[team]:
            _fail('SQUAD_TEAM_IDENTITY_MISMATCH')
        seen_teams.add(team)
        players = row.get('lineup')
        if not isinstance(players,list) or len(players) > MAX_SQUAD:
            _fail('SQUAD_LIMIT')
        projected = []
        for player in players:
            if not isinstance(player,dict):
                _fail('INVALID_SQUAD_PLAYER')
            ident,name = _int(player.get('player_id')),_name(player.get('player_name'))
            if ident in roster:
                _fail('DUPLICATE_ROSTER_PLAYER')
            roster[ident] = (team,name)
            item = {'player_id':ident,'player_name':name}
            if 'player_nickname' in player:
                nickname = player['player_nickname']
                if nickname is not None:
                    _name(nickname)
                item['player_nickname'] = nickname
            if 'jersey_number' in player:
                item['jersey_number'] = _int(player['jersey_number'],0,999)
            if 'country' in player:
                item['country'] = _named(player['country'])
            projected.append(item)
        result.append({'team_id':team,'team_name':row['team_name'],'lineup':projected})
    return result,roster


def _events(rows,teams,roster):
    if not isinstance(rows,list) or len(rows) > MAX_EVENTS:
        _fail('EVENT_LIMIT')
    seen_ids,seen_indices,types = set(),set(),{}
    missing = Counter({key:0 for key in OPTIONAL_EVENT_FIELDS})
    counts,projected = Counter(),[]
    for row in rows:
        if not isinstance(row,dict):
            _fail('INVALID_EVENT')
        ident = row.get('id')
        try:
            canonical_id = str(UUID(ident)) if isinstance(ident,str) else None
        except (ValueError,AttributeError):
            canonical_id = None
        if canonical_id is None or canonical_id != ident:
            _fail('INVALID_EVENT_UUID')
        index = _int(row.get('index'))
        if ident in seen_ids or index in seen_indices:
            _fail('DUPLICATE_EVENT_IDENTITY')
        seen_ids.add(ident)
        seen_indices.add(index)
        event_type = _named(row.get('type'))
        if event_type['id'] in types and types[event_type['id']] != event_type['name']:
            _fail('EVENT_TYPE_IDENTITY_MISMATCH')
        types[event_type['id']] = event_type['name']
        if len(types) > MAX_TYPES:
            _fail('EVENT_TYPE_LIMIT')
        item = {'id':ident,'index':index,'type':event_type}
        for key in OPTIONAL_EVENT_FIELDS:
            if key not in row:
                missing[key] += 1
                continue
            value = row[key]
            if key in ('team','player'):
                value = _named(value)
                if key == 'team' and (value['id'] not in teams or teams[value['id']] != value['name']):
                    _fail('EVENT_TEAM_IDENTITY_MISMATCH')
                if key == 'player' and (value['id'] not in roster or roster[value['id']][1] != value['name']):
                    _fail('EVENT_PLAYER_IDENTITY_MISMATCH')
            elif key == 'timestamp':
                if not isinstance(value,str) or not re.fullmatch(r'\d{2}:[0-5]\d:[0-5]\d(?:\.\d{1,6})?',value):
                    _fail('INVALID_RELATIVE_TIMESTAMP')
            else:
                value = _int(value,1,5) if key == 'period' else _int(value,0,59 if key == 'second' else 1000)
            item[key] = value
        if 'team' in item and 'player' in item and roster[item['player']['id']][0] != item['team']['id']:
            _fail('EVENT_PLAYER_TEAM_MISMATCH')
        counts[(item.get('team',{}).get('id'),item.get('period'),event_type['id'])] += 1
        projected.append(item)
    groups = [{'team_id':team,'period':period,'type_id':event_type,'count':count}
              for (team,period,event_type),count in sorted(counts.items(),key=lambda pair:tuple(-1 if x is None else x for x in pair[0]))]
    return projected,{'row_count':len(rows),'missing_fields':dict(missing),
                      'types':[{'id':ident,'name':name} for ident,name in sorted(types.items())],
                      'counts_by_team_period_type':groups}


def _parse(events_bytes,lineups_bytes,parent):
    teams = _parent_teams(parent)
    squads,roster = _squads(_json(lineups_bytes),teams)
    events,summary = _events(_json(events_bytes),teams,roster)
    projection = {'parser_version':VERSION,'match_id':3869685,'event_summary':summary,
                  'squads':squads,'scope':SCOPE,'attribution':ATTRIBUTION}
    if len(memory._canonical(projection)) > MAX_PROJECTION_BYTES:
        _fail('PROJECTION_LIMIT')
    return projection,events


def parse(events_bytes,lineups_bytes,*,parent):
    """Pure bounded projection; standalone parent identity is not DB proof."""
    return _parse(events_bytes,lineups_bytes,parent)[0]


def _page(events,offset,limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        _fail('INVALID_PAGE')
    return {'items':events[offset:offset+limit],'total':len(events),'offset':offset,'limit':limit,'parser_version':VERSION}


def event_page(events_bytes,lineups_bytes,*,parent,offset=0,limit=MAX_PAGE):
    """Regenerate native event fields in source array order; no inferred time."""
    return _page(_parse(events_bytes,lineups_bytes,parent)[1],offset,limit)


def _validated(db,raw_dir,payload):
    if not isinstance(payload,dict) or payload.get('parser_version') != VERSION:
        _fail('PARSER_VERSION_MISMATCH')
    bodies = binding.validate_and_load(db,raw_dir,payload)
    projection,events = _parse(bodies['events'],bodies['lineups'],payload['parent'])
    try:
        matches = memory._canonical(payload.get('projection')) == memory._canonical(projection)
    except (ValueError,TypeError,UnicodeError):
        matches = False
    if not matches:
        _fail('PROJECTION_RECONSTRUCTION_MISMATCH')
    return events


def make_validator(raw_dir):
    """Full receipt/parent/parser/projection validator for source_context."""
    root = Path(raw_dir).resolve()
    def validate(db,payload):
        _validated(db,root,payload)
    return validate


def read_event_page(db,raw_dir,payload,*,offset=0,limit=MAX_PAGE):
    """Bound source page with exact projection reconstruction; SELECTs only."""
    return _page(_validated(db,raw_dir,payload),offset,limit)
