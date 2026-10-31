"""Bounded football adapters. Transport retains exact bytes before parsing.

Only explicitly supported markets are normalized. Native payloads remain available
for richer account-dependent data without inventing unsupported capabilities.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import re
from urllib.parse import urlencode

from .core import ConnectorError


SPECS = {
    'football-data-couk': {
        'capabilities': ['fixtures', 'results', 'match_statistics', 'archival_odds'],
        'defaults': {'season': '2526', 'division': 'E0', 'max_records': 1000},
        'min_interval_seconds': 3600, 'live': False,
        'documentation_url': 'https://www.football-data.co.uk/notes.txt'},
    'football-data-org': {
        'capabilities': ['fixtures', 'results'],
        'defaults': {'competition': 'PL', 'max_records': 500},
        'min_interval_seconds': 60, 'live': False,
        'documentation_url': 'https://docs.football-data.org/general/v4/index.html'},
    'api-football': {
        'capabilities': ['fixtures', 'results', 'live_scores', 'prematch_odds'],
        'defaults': {'league_id': 39, 'season': 2026, 'include_odds': False,
                     'max_records': 500, 'max_pages': 5},
        'min_interval_seconds': 60, 'live': True,
        'documentation_url': 'https://www.api-football.com/documentation_v3'},
    'the-odds-api': {
        'capabilities': ['fixtures', 'bookmaker_odds', 'scores'],
        'defaults': {'sport': 'soccer_epl', 'regions': 'uk', 'markets': 'h2h',
                     'include_scores': True, 'max_records': 500},
        'min_interval_seconds': 60, 'live': False,
        'documentation_url': 'https://the-odds-api.com/liveapi/guides/v4/'},
    'sportmonks': {
        'capabilities': ['fixtures', 'results', 'prematch_odds'],
        'defaults': {'include_odds': False, 'max_records': 500, 'max_pages': 5},
        'min_interval_seconds': 60, 'live': False,
        'documentation_url': 'https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures'},
}

_DIVISIONS = frozenset(('E0','E1','E2','E3','EC','SC0','SC1','SC2','SC3','D1','D2',
    'I1','I2','SP1','SP2','F1','F2','N1','B1','P1','T1','G1'))
_BOOLS = {'include_odds', 'include_scores'}
_REGULATION = 'full_time_regulation'
_SETTLEMENT = 'regulation_90_minutes_plus_stoppage_time_excludes_extra_time_and_penalties'


def _error(code, message):
    raise ConnectorError(code, message)


def validate_config(provider, config):
    if provider not in SPECS:
        _error('CONNECTION_NOT_FOUND', 'Unknown football connector.')
    if not isinstance(config, dict):
        _error('INVALID_CONFIG', 'Connection configuration must be an object.')
    fields = {
        'football-data-couk': {'season','division','max_records'},
        'football-data-org': {'competition','date_from','date_to','max_records'},
        'api-football': {'league_id','season','date_from','date_to','include_odds','max_records','max_pages'},
        'the-odds-api': {'sport','regions','markets','include_scores','max_records'},
        'sportmonks': {'date_from','date_to','league_id','include_odds','max_records','max_pages'},
    }[provider]
    if set(config) - fields:
        _error('INVALID_CONFIG', 'Unsupported connection setting; use the registered provider fields.')
    out = {**SPECS[provider]['defaults'], **config}
    for key in _BOOLS & out.keys():
        if type(out[key]) is not bool:
            _error('INVALID_CONFIG', 'Optional retrieval switches must be true or false.')
    for key, maximum in (('max_records',2000),('max_pages',10),('league_id',100000000),('season',2100)):
        if key in out and not (provider == 'football-data-couk' and key == 'season'):
            if type(out[key]) is not int or not 1 <= out[key] <= maximum:
                _error('INVALID_CONFIG', 'A numeric connection setting is outside its supported bounds.')
    if provider == 'football-data-couk':
        if not isinstance(out['season'], str) or not re.fullmatch(r'\d{4}',out['season']):
            _error('INVALID_CONFIG', 'Historical season must be a four-digit code such as 2526.')
        if (int(out['season'][2:]) - int(out['season'][:2])) % 100 != 1:
            _error('INVALID_CONFIG', 'Historical season must contain consecutive years.')
        if not isinstance(out['division'],str) or out['division'] not in _DIVISIONS:
            _error('INVALID_CONFIG', 'Select a supported published football division.')
    if provider == 'football-data-org':
        if not isinstance(out['competition'],str) or not re.fullmatch(r'[A-Z0-9]{2,8}',out['competition']):
            _error('INVALID_CONFIG', 'Competition must be a registered short code such as PL.')
    if provider == 'api-football' and not 1900 <= out['season'] <= datetime.now(timezone.utc).year+1:
        _error('INVALID_CONFIG', 'API-FOOTBALL season must be a supported four-digit start year.')
    if provider == 'the-odds-api':
        if not isinstance(out['sport'],str) or not re.fullmatch(r'soccer_[a-z0-9_]{1,70}',out['sport']):
            _error('INVALID_CONFIG', 'Select a football sport key from the provider catalogue.')
        for field, allowed in (('regions',{'uk','eu','us','us2','au'}),('markets',{'h2h','totals','spreads'})):
            if not isinstance(out[field],str) or not out[field] or not set(out[field].split(',')) <= allowed:
                _error('INVALID_CONFIG', 'Unsupported odds region or market.')
            out[field] = ','.join(dict.fromkeys(out[field].split(',')))
    if provider in ('football-data-org','api-football','sportmonks'):
        today = datetime.now(timezone.utc).date()
        # football-data.org dateTo is exclusive; the other providers use inclusive ranges.
        out.setdefault('date_from',today.isoformat())
        out.setdefault('date_to',(today+timedelta(days=1 if provider == 'football-data-org' else 0)).isoformat())
        try:
            start,end = date.fromisoformat(out['date_from']),date.fromisoformat(out['date_to'])
        except (ValueError,TypeError):
            _error('INVALID_CONFIG', 'Use ISO dates YYYY-MM-DD for the fixture range.')
        if end < start or (end-start).days > 31 or (provider == 'football-data-org' and end == start):
            _error('INVALID_CONFIG', 'Select an ordered fixture range of at most 31 days; football-data.org dateTo is exclusive.')
    return out


def _get(transport, url, headers, check):
    check()
    try:
        doc = transport.get(url, headers=headers)
    except ConnectorError:
        raise
    except Exception as exc:
        code = getattr(exc,'code',None)
        if code == 429:
            raise ConnectorError('RATE_LIMITED','Provider quota exhausted; retry from Connections.',retry_after=60,http_status=429) from None
        if code in (401,403):
            raise ConnectorError('AUTH_REJECTED','The account cannot access this endpoint; check Connections.',http_status=code) from None
        raise ConnectorError('NETWORK_UNAVAILABLE','Provider retrieval failed; cached records remain available.',retry_after=60) from None
    check()
    return doc


def _json(doc, expected=dict):
    data = doc.json()
    if not isinstance(data,expected):
        _error('SCHEMA_CHANGED','The provider response does not match its documented fixture schema.')
    return data


def _text(value):
    return str(value).strip() if value is not None else ''


def _number(value, *, integer=False):
    if value is None or value == '' or isinstance(value,bool):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or (integer and (number < 0 or number != number.to_integral_value())):
            return None
        result = int(number) if integer else float(number)
        return result if integer or math.isfinite(result) else None
    except (InvalidOperation,ValueError,OverflowError):
        return None


def _utc(value, *, documented_utc=False):
    if value in (None,''):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:
            if not documented_utc:
                return None
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    except (ValueError,TypeError):
        return None


def _record(provider, native, doc, *, identity, competition, season, home, away, day,
            kickoff=None, local_time=None, status='scheduled', scores=(None,None), attributes=None):
    if not all(_text(v) for v in (competition,season,home,away)) or home.casefold() == away.casefold():
        _error('INVALID_RECORD','The provider omitted or ambiguously identified a fixture participant.')
    try:
        date.fromisoformat(day)
    except (ValueError,TypeError):
        _error('INVALID_RECORD','The provider fixture date is missing or invalid; no date was invented.')
    attrs = {'provider_id':provider, **(attributes or {})}
    if identity is None:
        identity = hashlib.sha256(json.dumps([competition,season,home,away],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        attrs.update(native_id_missing=True,identity_basis='competition_season_ordered_participants')
    return {'source_record_id':str(identity),'sport':'football','competition':_text(competition),
            'season':_text(season),'home':home,'away':away,'event_date':day,'kickoff_utc':kickoff,
            'source_local_time':local_time,'status':status,'score_home':scores[0],'score_away':scores[1],
            'statistics':{},'attributes':attrs,'odds':[], 'source_document_sha256':doc.sha256,'original':native}


def _odds(provider, feed, selection, value, *, market='1x2',line=None,quote_at=None,**extra):
    if not _text(provider):
        return None
    price = _number(value)
    if price is None or price <= 1:
        return None
    return {'provider':str(provider),'feed':feed,'market':market,'period':_REGULATION,
            'selection':selection,'line':line,'decimal_odds':price,'state':'prematch',
            'settlement_rules':_SETTLEMENT,'quote_at':quote_at,'original_odds':str(value),**extra}


def _finish(records, limit):
    seen = {}
    for record in records:
        key = record['source_record_id']
        if key in seen:
            _error('IDENTITY_COLLISION','Multiple source rows share a fixture identity; ambiguous fixtures were not joined. Narrow the connection scope.')
        seen[key] = record
    if len(records) > limit:
        records = records[:limit]
        for record in records:
            record['attributes']['retrieval_truncated'] = True
    return records


def _csv_fetch(config,transport,check):
    doc = _get(transport,'https://www.football-data.co.uk/mmz4281/'+config['season']+'/'+config['division']+'.csv',None,check)
    body = doc.text()
    if body.lstrip().lower().startswith(('<html','<!doctype')):
        _error('UNEXPECTED_HTML','The source returned HTML instead of its published CSV.')
    reader = csv.DictReader(io.StringIO(body,newline=''))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not {'Div','Date','HomeTeam','AwayTeam'} <= set(reader.fieldnames):
        _error('SCHEMA_CHANGED','The CSV is missing its documented fixture columns.')
    start = int(config['season'][:2]); year = 1900+start if start >= 90 else 2000+start
    season = str(year)+'/'+str(year+1)
    records = []
    bookmakers = ('B365','PS','BW','IW','WH','VC','BV','LB','SJ','GB','SB','BS','SO','BFD','BMGM','CL','BFE')
    stat_names={'HS':'shots_home','AS':'shots_away','HST':'shots_on_target_home','AST':'shots_on_target_away',
                'HC':'corners_home','AC':'corners_away','HF':'fouls_home','AF':'fouls_away',
                'HY':'yellow_cards_home','AY':'yellow_cards_away','HR':'red_cards_home','AR':'red_cards_away'}
    for row in reader:
        check()
        if not any(_text(v) for v in row.values()):
            continue
        if None in row or row.get('Div') != config['division']:
            _error('SCHEMA_CHANGED','A CSV row has extra columns or belongs to another division.')
        try:
            day = datetime.strptime(row['Date'],'%d/%m/%Y' if len(row['Date']) == 10 else '%d/%m/%y').date().isoformat()
        except (ValueError,TypeError):
            _error('INVALID_RECORD','A CSV fixture date is invalid.')
        home,away = _text(row['HomeTeam']),_text(row['AwayTeam'])
        scores = (_number(row.get('FTHG'),integer=True),_number(row.get('FTAG'),integer=True))
        complete = all(value is not None for value in scores)
        record = _record('football-data-couk',row,doc,identity=None,competition=row['Div'],season=season,
            home=home,away=away,day=day,local_time=row.get('Time') or None,
            status='historical_result' if complete else 'scheduled',scores=scores,
            attributes={'data_origin':'historical_archive','timezone_unknown':True,'quote_timestamps_available':False,
                        'score_scope':'regulation','source_attribution':'Football-Data.co.uk'})
        record['statistics']={name:_number(row.get(col),integer=True) for col,name in stat_names.items() if row.get(col) not in (None,'')}
        for book in bookmakers:
            for phase,marker in (('opening',''),('closing','C')):
                for suffix,selection in (('H','home'),('D','draw'),('A','away')):
                    col=book+marker+suffix
                    odd=_odds('football-data-label:'+book,'football-data-couk-archive',selection,row.get(col),
                              archive_phase=phase,source_column=col,bookmaker_label=book,source_document_sha256=doc.sha256)
                    if odd:
                        record['odds'].append(odd)
                # The source total-goals columns explicitly refer to 2.5 goals.
                total_prefix = 'P' if book == 'PS' else book
                for symbol,selection in (('>','over'),('<','under')):
                    col=total_prefix+marker+symbol+'2.5'
                    odd=_odds('football-data-label:'+book,'football-data-couk-archive',selection,row.get(col),
                        market='total_goals',line=2.5,archive_phase=phase,source_column=col,bookmaker_label=book,source_document_sha256=doc.sha256)
                    if odd:
                        record['odds'].append(odd)
        if day >= '2025-07-23' and any(o['bookmaker_label']=='PS' for o in record['odds']):
            record['attributes']['source_warnings']=['The source warns Pinnacle prices may be stale from 2025-07-23; exact quote times are unavailable.']
        records.append(record)
        if len(records) > 20000:
            _error('RECORD_LIMIT','The season file exceeds the supported record bound.')
    return _finish(records,config['max_records'])


def _fdo(config,secret,transport,check):
    query=urlencode({'dateFrom':config['date_from'],'dateTo':config['date_to']})
    doc=_get(transport,'https://api.football-data.org/v4/competitions/'+config['competition']+'/matches?'+query,{'X-Auth-Token':secret},check)
    data=_json(doc)
    if data.get('errorCode'):
        _error('AUTH_REJECTED','The configured football-data.org account cannot access this fixture scope.')
    if not isinstance(data.get('matches'),list):
        _error('SCHEMA_CHANGED','The matches collection is missing from football-data.org.')
    records=[]
    for row in data['matches']:
        check()
        kickoff=_utc(row.get('utcDate'))
        if not kickoff:
            _error('INVALID_RECORD','A football-data.org fixture omitted its UTC date.')
        state=row.get('status')
        status='historical_result' if state in ('FINISHED','AWARDED') else 'live' if state in ('IN_PLAY','PAUSED','SUSPENDED') else 'cancelled' if state == 'CANCELLED' else 'scheduled'
        score=row.get('score') or {}; full=score.get('fullTime') or {}
        season=row.get('season') or data.get('season') or {}
        season_name=(season.get('startDate','')[:4]+'/'+season.get('endDate','')[:4]) if season.get('startDate') and season.get('endDate') else 'id:'+str(season.get('id','unspecified'))
        competition=row.get('competition') or data.get('competition') or {}
        record=_record('football-data-org',row,doc,identity=row.get('id'),competition=competition.get('code') or config['competition'],season=season_name,
            home=_text((row.get('homeTeam') or {}).get('name')),away=_text((row.get('awayTeam') or {}).get('name')),
            day=kickoff[:10],kickoff=kickoff,status=status,scores=(_number(full.get('home'),integer=True),_number(full.get('away'),integer=True)),
            attributes={'source_status':state,'native_competition_id':competition.get('id'),'score_duration':score.get('duration'),
                'regular_time_score':score.get('regularTime'),'matchday':row.get('matchday'),'stage':row.get('stage')})
        record['venue']=row.get('venue')
        records.append(record)
    return _finish(records,config['max_records'])


def _api_payload(doc):
    data=_json(doc)
    if data.get('errors'):
        text=json.dumps(data['errors']).lower()
        if any(word in text for word in ('rate','limit','quota')):
            raise ConnectorError('RATE_LIMITED','API-FOOTBALL account quota exhausted.',retry_after=60)
        _error('AUTH_REJECTED','API-FOOTBALL rejected the key, subscription or requested coverage. Check Connections.')
    if not isinstance(data.get('response'),list):
        _error('SCHEMA_CHANGED','API-FOOTBALL response collection is missing.')
    return data


def _api_football(config,secret,transport,check):
    headers={'x-apisports-key':secret}
    query={'league':config['league_id'],'season':config['season'],'from':config['date_from'],'to':config['date_to'],'timezone':'UTC'}
    doc=_get(transport,'https://v3.football.api-sports.io/fixtures?'+urlencode(query),headers,check)
    data=_api_payload(doc); records=[]
    for row in data['response']:
        check()
        fixture=row.get('fixture') or {}; kickoff=_utc(fixture.get('date')); state=(fixture.get('status') or {}).get('short')
        if not kickoff:
            _error('INVALID_RECORD','An API-FOOTBALL fixture omitted its timezone-aware date.')
        league=row.get('league') or {}; teams=row.get('teams') or {}; goals=row.get('goals') or {}
        status='historical_result' if state in ('FT','AET','PEN','AWD','WO') else 'live' if state in ('1H','HT','2H','ET','BT','P','LIVE','INT','SUSP') else 'cancelled' if state in ('CANC','ABD') else 'scheduled'
        record=_record('api-football',row,doc,identity=fixture.get('id'),competition=str(league.get('id',config['league_id'])),season=str(league.get('season',config['season'])),
            home=_text((teams.get('home') or {}).get('name')),away=_text((teams.get('away') or {}).get('name')),
            day=kickoff[:10],kickoff=kickoff,status=status,scores=(_number(goals.get('home'),integer=True),_number(goals.get('away'),integer=True)),
            attributes={'source_status':state,'competition_name':league.get('name'),'round':league.get('round'),
                'elapsed':(fixture.get('status') or {}).get('elapsed'),'regulation_score':(row.get('score') or {}).get('fulltime'),
                'native_home_id':(teams.get('home') or {}).get('id'),'native_away_id':(teams.get('away') or {}).get('id')})
        record['venue']=(fixture.get('venue') or {}).get('name'); records.append(record)
    records=_finish(records,config['max_records'])
    if config['include_odds'] and records:
        by_id={r['source_record_id']:r for r in records}
        day=date.fromisoformat(config['date_from']); last=date.fromisoformat(config['date_to']); page=1
        for request_index in range(config['max_pages']):
            odds_query={'league':config['league_id'],'season':config['season'],'date':day.isoformat(),'timezone':'UTC','page':page,'bet':1}
            odds_doc=_get(transport,'https://v3.football.api-sports.io/odds?'+urlencode(odds_query),headers,check)
            odds_data=_api_payload(odds_doc)
            for event in odds_data['response']:
                check(); record=by_id.get(str((event.get('fixture') or {}).get('id')))
                if not record:
                    continue
                for book in event.get('bookmakers') or []:
                    if book.get('id') is None:
                        continue
                    for bet in book.get('bets') or []:
                        if bet.get('id') != 1:
                            continue
                        for value in bet.get('values') or []:
                            selection={'Home':'home','Draw':'draw','Away':'away'}.get(value.get('value'))
                            odd=_odds('api-football:bookmaker:'+str(book.get('id')),'api-football-prematch',selection,value.get('odd'),
                                bookmaker_label=book.get('name'),source_document_sha256=odds_doc.sha256,provider_update_at=_utc(event.get('update')))
                            if selection and odd:
                                record['odds'].append(odd)
            total=(odds_data.get('paging') or {}).get('total',1)
            if type(total) is not int or total < 0:
                _error('SCHEMA_CHANGED','The odds pagination metadata is invalid.')
            if page >= total:
                day += timedelta(days=1); page=1
                if day > last:
                    break
            else:
                page += 1
            if request_index == config['max_pages']-1:
                for record in records:
                    record['attributes']['odds_retrieval_truncated']=True
    return records


def _odds_api(config,secret,transport,check):
    base='https://api.the-odds-api.com/v4/sports/'+config['sport']
    doc=_get(transport,base+'/odds/?'+urlencode({'apiKey':secret,'regions':config['regions'],'markets':config['markets'],'oddsFormat':'decimal','dateFormat':'iso'}),None,check)
    rows=_json(doc,list); score_map={}; score_doc=None; score_error=None
    if config['include_scores']:
        try:
            score_doc=_get(transport,base+'/scores/?'+urlencode({'apiKey':secret,'dateFormat':'iso'}),None,check)
            score_map={str(row['id']):row for row in _json(score_doc,list) if row.get('id')}
        except ConnectorError as exc:
            if exc.code not in ('AUTH_REJECTED','HTTP_ERROR'):
                raise
            score_error=exc.code
    records=[]
    for row in rows:
        check(); kickoff=_utc(row.get('commence_time'))
        if not kickoff:
            _error('INVALID_RECORD','An Odds API event omitted its timezone-aware kickoff.')
        score=score_map.get(str(row.get('id')),{}); named_scores={s.get('name'):_number(s.get('score'),integer=True) for s in score.get('scores') or []}
        status='historical_result' if score.get('completed') is True else 'live' if score.get('completed') is False and named_scores else 'scheduled'
        attrs={'status_unverified':not bool(score),'season_unknown':True}
        if score_doc:
            attrs['related_source_sha256']=[score_doc.sha256]
        if score_error:
            attrs['scores_unavailable']=score_error
        record=_record('the-odds-api',row,doc,identity=row.get('id'),competition=row.get('sport_key') or config['sport'],season='unspecified',
            home=_text(row.get('home_team')),away=_text(row.get('away_team')),day=kickoff[:10],kickoff=kickoff,status=status,
            scores=(named_scores.get(row.get('home_team')),named_scores.get(row.get('away_team'))),attributes=attrs)
        for book in row.get('bookmakers') or []:
            for market in book.get('markets') or []:
                key=market.get('key')
                if key not in ('h2h','totals','spreads'):
                    continue  # Lay and outright prices need different payoff contracts.
                for outcome in market.get('outcomes') or []:
                    selection={'Draw':'draw','Over':'over','Under':'under',record['home']:'home',record['away']:'away'}.get(outcome.get('name'))
                    line=_number(outcome.get('point')) if key != 'h2h' else None
                    if not selection or (key != 'h2h' and line is None):
                        continue
                    quote=_utc(market.get('last_update')) or _utc(book.get('last_update'))
                    odd=_odds(book.get('key'),'the-odds-api-current',selection,outcome.get('price'),market={'h2h':'1x2','totals':'total_goals','spreads':'asian_handicap'}[key],line=line,
                        quote_at=quote,bookmaker_label=book.get('title'),timestamp_basis='market_or_bookmaker_update',source_document_sha256=doc.sha256)
                    if odd:
                        odd['state']='in_play' if status == 'live' else 'prematch' if status == 'scheduled' and not attrs['status_unverified'] else 'unknown'
                        record['odds'].append(odd)
        records.append(record)
    return _finish(records,config['max_records'])


def _sportmonks(config,secret,transport,check):
    records=[]
    for page in range(1,config['max_pages']+1):
        query={'include':'participants;scores;state;league;season;venue'+(';odds' if config['include_odds'] else ''),'per_page':50,'page':page,'timezone':'UTC'}
        if config.get('league_id'):
            query['filters']='fixtureLeagues:'+str(config['league_id'])
        path='/date/'+config['date_from'] if config['date_from'] == config['date_to'] else '/between/date/'+config['date_from']+'/'+config['date_to']
        doc=_get(transport,'https://api.sportmonks.com/v3/football/fixtures'+path+'?'+urlencode(query),{'Authorization':secret},check)
        data=_json(doc)
        if not isinstance(data.get('data'),list):
            _error('SCHEMA_CHANGED','The Sportmonks fixture collection is unavailable; check account coverage.')
        for row in data['data']:
            check(); participants=row.get('participants') or []
            teams={p.get('meta',{}).get('location'):p for p in participants}
            state=(row.get('state') or {}).get('developer_name') or {1:'NS',2:'INPLAY_1ST_HALF',3:'HT',4:'BREAK',5:'FT',6:'INPLAY_ET',7:'AET',8:'FT_PEN',9:'INPLAY_PENALTIES',10:'POSTPONED',11:'SUSPENDED',12:'CANCELLED',13:'TBA',14:'WO'}.get(row.get('state_id'),'UNKNOWN')
            status='historical_result' if state in ('FT','AET','FT_PEN','WO','AWARDED') else 'live' if state.startswith('INPLAY') or state in ('HT','BREAK','SUSPENDED') else 'cancelled' if state in ('CANCELLED','ABANDONED') else 'scheduled'
            kickoff=_utc(row.get('starting_at'),documented_utc=True)
            if not kickoff:
                _error('INVALID_RECORD','A Sportmonks fixture omitted its documented UTC start date.')
            current={}
            for score in row.get('scores') or []:
                if score.get('description') == 'CURRENT':
                    item=score.get('score') or {}; current[item.get('participant')]=_number(item.get('goals'),integer=True)
            league=row.get('league') or {}; season=row.get('season') or {}
            record=_record('sportmonks',row,doc,identity=row.get('id'),competition=str(row.get('league_id') or league.get('id') or 'unspecified'),season=season.get('name') or 'id:'+str(row.get('season_id','unspecified')),
                home=_text(teams.get('home',{}).get('name')),away=_text(teams.get('away',{}).get('name')),day=kickoff[:10],kickoff=kickoff,status=status,
                scores=(current.get('home'),current.get('away')),attributes={'source_status':state,'status_unverified':state=='UNKNOWN','competition_name':league.get('name'),'native_home_id':teams.get('home',{}).get('id'),'native_away_id':teams.get('away',{}).get('id')})
            record['venue']=(row.get('venue') or {}).get('name')
            for raw in row.get('odds') or []:
                if raw.get('market_id') != 1 or raw.get('stopped') is True or raw.get('bookmaker_id') is None:
                    continue
                selection={'1':'home','Home':'home','X':'draw','Draw':'draw','2':'away','Away':'away'}.get(raw.get('label'))
                odd=_odds('sportmonks:bookmaker:'+str(raw.get('bookmaker_id')),'sportmonks-prematch',selection,raw.get('value'),source_document_sha256=doc.sha256)
                if odd and selection:
                    record['odds'].append(odd)
            records.append(record)
        more=(data.get('pagination') or {}).get('has_more',False)
        if type(more) is not bool:
            _error('SCHEMA_CHANGED','The Sportmonks pagination metadata is invalid.')
        if not more:
            break
        if page == config['max_pages'] or len(records) >= config['max_records']:
            for record in records:
                record['attributes']['retrieval_truncated']=True
            break
    return _finish(records,config['max_records'])


def fetch(provider_id, config, secret, transport, check):
    """Fetch a finite scope. Account authentication is never inferred from a card."""
    config=validate_config(provider_id,config)
    if provider_id != 'football-data-couk':
        if not isinstance(secret,str) or not secret.strip():
            _error('NEEDS_KEY','Save the provider API key in server Connections before checking or importing this source.')
        if len(secret) > 4096 or '\r' in secret or '\n' in secret:
            _error('INVALID_KEY','The saved provider credential is not a valid request token.')
    check()
    try:
        if provider_id == 'football-data-couk':
            return _csv_fetch(config,transport,check)
        return {'football-data-org':_fdo,'api-football':_api_football,'the-odds-api':_odds_api,'sportmonks':_sportmonks}[provider_id](config,secret,transport,check)
    except ConnectorError:
        raise
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError,IndexError):
        raise ConnectorError('SCHEMA_CHANGED','The provider payload could not be normalized; original response evidence was retained.') from None
