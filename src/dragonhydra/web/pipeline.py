"""Explicit one-shot fetch/import/summary commands; no permanent daemon."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import uuid4
from .contracts import FetchPolicy, HandoffManifest, PipelineError, utcnow, timestamp
from .fetch import fetch, _request
from .robots import evaluate_robots
from .provenance import bounded_file, checkpoint, digest, encode, exclusive_json
from .json_api import parse_json
from .terms import allow_source, load_sources
from .validation import validate_observation
from .odds import OddsObservation, probability
from ..config import PROJECT_ROOT
from ..storage.intelligence import IntelligenceStore, PresentationStore, sql_connection
from .bridge import bridge_event, manifest_origin


def new_job(kind, source_id):
    return {'job_id':uuid4().hex, 'job_type':kind, 'started_at':utcnow(), 'finished_at':None,
            'status':'RUNNING','source_id':source_id,'items_seen':0,'items_accepted':0,
            'items_rejected':0,'error_count':0,'checkpoint_path':None}


def capture(root=PROJECT_ROOT):
    sources = load_sources(root)
    source = sources['openfootball']
    job = new_job('FETCH_PUBLIC_API', source['source_id'])
    ops = PresentationStore()
    ops.save_job(job)
    try:
        policy = FetchPolicy(source['source_id'], source['allowed_urls'][0], 'one historical match file for local research')
        body, evidence = fetch(policy, source)
        handoff_id = uuid4().hex
        download = root / 'runtime/handoff/browser_downloads' / f'{handoff_id}.json'
        with download.open('xb') as stream:
            stream.write(body)
        manifest = HandoffManifest(handoff_id=handoff_id, created_at=utcnow(), created_by='Codex terminal Python fetch',
            source_url=policy.url,source_title=source['name'],source_type='PUBLIC_DATASET',
            capture_method='PYTHON_ALLOWED_FETCH_BROWSER_UNAVAILABLE', download_path=download.relative_to(root).as_posix(),
            content_hash=evidence['content_hash'], observed_at=evidence['retrieved_at'], event_time_if_known=None,
            terms_note='Public JSON access documented in upstream README; CC0 license reviewed.',
            robots_note=evidence['robots']['robots_status'],license_note=source['license_status'],
            confidence=0.9,processing_status='PENDING',source_id=source['source_id'],content_type=evidence['content_type'])
        exclusive_json(root / 'runtime/handoff/manifests' / f'{handoff_id}.fetch.json', dict(evidence, policy=asdict(policy)))
        exclusive_json(root / 'runtime/handoff/manifests' / f'{handoff_id}.json', manifest)
        exclusive_json(root / 'runtime/handoff/browser_inbox' / f'{handoff_id}.json', manifest)
        bridge_event(root,'CLI_FETCHED','CLI_FETCH',handoff_id)
        job.update(status='SUCCEEDED',finished_at=utcnow(),items_seen=1,items_accepted=1,
                   handoff_id=handoff_id,source_url=policy.url,content_hash=digest(body))
        store = IntelligenceStore()
        with sql_connection() as conn:
            store.append(conn,'sources',source['source_id'],source,source['source_id'],job['finished_at'])
            store.append(conn,'source_terms',source['source_id'],dict(source,robots=evidence['robots']),source['source_id'],job['finished_at'])
            store.append(conn,'scrape_runs',job['job_id'],job,source['source_id'],job['finished_at'])
            conn.commit()
        job['checkpoint_path'] = str(checkpoint(root,'fetch',dict(job,evidence=evidence)))
        return manifest
    except Exception as error:
        job.update(status='FAILED',finished_at=utcnow(),error_count=1,
                   reason=str(error) if isinstance(error,PipelineError) else type(error).__name__)
        checkpoint(root,'fetch-failed',job)
        raise
    finally:
        ops.save_job(job)


def normalize_matches(body, manifest, source, robots):
    rows = parse_json(body)
    if manifest.source_id == 'openfootball':
        return normalize_openfootball(rows, manifest, source, robots)
    if manifest.source_id != 'statsbomb-open' or not isinstance(rows,list) or not 1 <= len(rows) <= 100:
        raise PipelineError('SCHEMA_CHANGED')
    normalized = []
    for row in rows:
        try:
            mid = row['match_id']
            home, away = row['home_team'], row['away_team']
            if type(mid) is not int or type(home['home_team_id']) is not int or type(away['away_team_id']) is not int:
                raise ValueError()
            if not home['home_team_name'] or not away['away_team_name']:
                raise ValueError()
            for k in ('home_score','away_score'):
                if type(row[k]) is not int or row[k]<0:
                    raise ValueError()
            fixture_id = 'statsbomb:match:' + str(mid)
            record = {'fixture_id':fixture_id,'entity_id':fixture_id,
                'home_entity_id':f'statsbomb:team:{home["home_team_id"]}',
                'away_entity_id':f'statsbomb:team:{away["away_team_id"]}',
                'home_team':home['home_team_name'],'away_team':away['away_team_name'],
                'home_score':row['home_score'],'away_score':row['away_score'],
                'match_date':row['match_date'],'kickoff_local':row['kick_off'],
                'event_at':None, 'event_timezone_note':'Source fixture timezone not independently established; no UTC inferred.',
                'match_status':row.get('match_status','unknown'),
                'source_updated_at':row.get('last_updated'),
                'observed_at':manifest.observed_at,'available_at':manifest.observed_at,'updated_at':utcnow(),
                'target_as_of_at':None,'source_id':manifest.source_id,'source_url':manifest.source_url,
                'source_type':manifest.source_type,'retrieved_at':manifest.observed_at,'content_hash':manifest.content_hash,
                'parser_version':'statsbomb-match/1.0','license_status':source['license_status'],
                'terms_status':source['terms_status'],'robots_status':robots['robots_status'],
                'content_type':manifest.content_type,'confidence':min(manifest.confidence,0.9),'synthetic':False}
            from datetime import date,time
            date.fromisoformat(record['match_date'])
            time.fromisoformat(record['kickoff_local'])
            normalized.append(record)
        except (KeyError,TypeError,ValueError):
            raise PipelineError('SCHEMA_CHANGED') from None
    return normalized


def normalize_openfootball(document, manifest, source, robots):
    from datetime import date
    import unicodedata
    try:
        rows = document['matches']
        competition = document['name']
        if not isinstance(rows,list) or not 1 <= len(rows) <= 500 or not isinstance(competition,str):
            raise ValueError()
        normalized = []
        for row in rows:
            teams = [row['team1'],row['team2']]
            if any(not isinstance(t,str) or not t.strip() or len(t)>120 for t in teams):
                raise ValueError()
            date.fromisoformat(row['date'])
            score = row.get('score',{}).get('ft')
            if score is not None and (not isinstance(score,list) or len(score)!=2 or any(type(v) is not int or v<0 for v in score)):
                raise ValueError()
            entities = ['openfootball:team:'+digest(unicodedata.normalize('NFKC',t).casefold().encode())[:24] for t in teams]
            key = 'openfootball:match:'+digest(encode([competition,row.get('round'),*entities]))[:32]
            normalized.append({'fixture_id':key,'entity_id':key,'home_entity_id':entities[0],'away_entity_id':entities[1],
                'home_team':teams[0],'away_team':teams[1],'home_score':score[0] if score else None,'away_score':score[1] if score else None,
                'competition':competition,'round':row.get('round'),'match_date':row['date'],'kickoff_local':row.get('time'),
                'event_at':None,'event_timezone_note':'Date/local time only; timezone unverified. UTC event_at remains null.',
                'match_status':'FINISHED' if score else 'UNKNOWN','source_updated_at':None,
                'observed_at':manifest.observed_at,'available_at':manifest.observed_at,'updated_at':utcnow(),'target_as_of_at':None,
                'source_id':manifest.source_id,'source_url':manifest.source_url,'source_type':manifest.source_type,
                'retrieved_at':manifest.observed_at,'content_hash':manifest.content_hash,'parser_version':'openfootball/1.0',
                'license_status':source['license_status'],'terms_status':source['terms_status'],'robots_status':robots['robots_status'],
                'content_type':manifest.content_type,'confidence':min(manifest.confidence,0.8),'synthetic':False})
        if len({r['fixture_id'] for r in normalized}) != len(normalized):
            raise ValueError()
        return normalized
    except (KeyError,TypeError,ValueError):
        raise PipelineError('SCHEMA_CHANGED') from None


def process_item(path, root=PROJECT_ROOT):
    job = new_job('IMPORT_BROWSER_HANDOFF','unknown')
    ops, store = PresentationStore(), IntelligenceStore()
    ops.save_job(job)
    original_hash = None
    origin, handoff_id = 'NONE', None
    try:
        raw_manifest = bounded_file(path,root/'runtime/handoff/browser_inbox',32000)
        original_hash = digest(raw_manifest)
        manifest = HandoffManifest(**parse_json(raw_manifest))
        origin, handoff_id = manifest_origin(manifest), manifest.handoff_id
        if origin == 'DESKTOP_BROWSER':
            note_path = root/'runtime/handoff/browser_notes'/f'{handoff_id}.json'
            note = parse_json(bounded_file(note_path,root/'runtime/handoff/browser_notes',32000))
            if (note.get('SOURCE_URL') != manifest.source_url or note.get('DESKTOP_STAGE') != 'CONFIRMED'
                    or not note.get('BROWSER_EVIDENCE') or note.get('CONTENT_HASH') != manifest.content_hash):
                raise PipelineError('DESKTOP_EVIDENCE_REQUIRED')
            bridge_event(root,'DESKTOP_CONFIRMED',origin,handoff_id,desktop_evidence=str(note_path))
        bridge_event(root,'PROCESSING',origin,handoff_id)
        job['source_id'] = manifest.source_id
        source = load_sources(root).get(manifest.source_id)
        if source is None:
            raise PipelineError('SOURCE_UNKNOWN')
        allow_source(source, manifest.source_url)
        if manifest.source_type != 'PUBLIC_DATASET' or manifest.content_type not in source['content_types']:
            raise PipelineError('CONTENT_TYPE_UNEXPECTED')
        body = bounded_file(root/manifest.download_path,root/'runtime/handoff/browser_downloads')
        if digest(body) != manifest.content_hash:
            raise PipelineError('HASH_MISMATCH')
        # Recheck independently instead of trusting a manifest's self-reported allowance.
        url = f'https://{source["host"]}/robots.txt'
        rob,_,status = _request(FetchPolicy(manifest.source_id,url,'robots recheck',max_bytes=100000,content_type_allowlist=('text/plain',)),allow_404=True)
        robots = evaluate_robots(rob.decode(),manifest.source_url,'DRAGONHYDRA-Research/1.0',status)
        if robots['robots_status'] not in ('ALLOWED','ABSENT'):
            raise PipelineError('ROBOTS_BLOCKED')
        rows = normalize_matches(body,manifest,source,robots)
        job['items_seen'] = len(rows)
        with sql_connection() as conn:
            prior_receipt = store.previous(conn,'handoff_items',manifest.handoff_id)
            if prior_receipt and prior_receipt.get('manifest_hash') != original_hash:
                raise PipelineError('HANDOFF_ID_COLLISION')
            for record in rows:
                key = record['fixture_id']
                prior = store.previous(conn,'fixtures',key)
                duplicate = bool(prior and prior['content_hash']==record['content_hash'])
                conflict = bool(prior and prior['observed_at']==record['observed_at'] and
                                (prior['home_score'],prior['away_score']) != (record['home_score'],record['away_score']))
                verdict = validate_observation(record,source,duplicate=duplicate,conflict=conflict)
                record['validation'] = asdict(verdict)
                unique = digest(encode([key,record['content_hash'],record['observed_at']]))
                store.append(conn,'web_observations',key,record,manifest.source_id,record['available_at'],dedup_key=unique)
                if verdict.decision in ('REJECT','QUARANTINE'):
                    job['items_rejected'] += 1
                    if conflict:
                        store.append(conn,'conflicts',key,record,manifest.source_id,record['available_at'])
                    continue
                for side in ('home','away'):
                    entity = {'entity_id':record[side+'_entity_id'],'name':record[side+'_team'],'entity_type':'team',
                              'source_id':manifest.source_id,'source_url':manifest.source_url,'content_hash':manifest.content_hash,
                              'observed_at':manifest.observed_at,'available_at':manifest.observed_at}
                    store.append(conn,'entities',entity['entity_id'],entity,manifest.source_id,manifest.observed_at)
                store.append(conn,'fixtures',key,record,manifest.source_id,record['available_at'],dedup_key=unique)
                job['items_accepted'] += 1
            job.update(status='SUCCEEDED' if job['items_accepted'] else 'NO_NEW_RECORDS',finished_at=utcnow(),handoff_id=manifest.handoff_id,
                       manifest_hash=original_hash,content_hash=manifest.content_hash)
            store.append(conn,'handoff_items',manifest.handoff_id,job,manifest.source_id,job['finished_at'])
            store.append(conn,'processing_runs',job['job_id'],job,manifest.source_id,job['finished_at'])
            conn.commit()
        # SQL commit is authoritative; replay is idempotent if filesystem work fails here.
        receipt = checkpoint(root,'sql-ingestion',job)
        job['checkpoint_path'] = str(receipt)
        destination = root/'runtime/handoff/processed'/f'{path.stem}-{job["job_id"]}.json'
        path.rename(destination)
        exclusive_json(destination.with_suffix('.receipt.json'),dict(job,processing_status='PROCESSED'))
        bridge_event(root,'PROCESSED',origin,handoff_id,str(destination.with_suffix('.receipt.json')))
    except Exception as error:
        reason = str(error) if isinstance(error,PipelineError) else type(error).__name__
        job.update(status='FAILED',finished_at=utcnow(),error_count=1,reason=reason,manifest_hash=original_hash)
        checkpoint(root,'handoff-failed',job)
        bridge_event(root,'FAILED',origin,handoff_id)
        if path.is_file() and path.resolve().is_relative_to((root/'runtime/handoff/browser_inbox').resolve()):
            destination = root/'runtime/handoff/failed'/f'{path.stem}-{job["job_id"]}.json'
            path.rename(destination)
            exclusive_json(destination.with_suffix('.receipt.json'),dict(job,processing_status='FAILED'))
    finally:
        ops.save_job(job)
    return job


def process_inbox(root=PROJECT_ROOT, limit=10):
    if not 1 <= limit <= 25:
        raise ValueError('Bounded batch required')
    # Exclusive process lock; crash leaves evidence and requires deliberate recovery.
    lock = root/'runtime/handoff/cli_inbox/processor.lock'
    with lock.open('x') as stream:
        stream.write(utcnow())
    try:
        return [process_item(p,root) for p in sorted((root/'runtime/handoff/browser_inbox').glob('*.json'))[:limit]]
    finally:
        lock.unlink()


def synthetic_odds(root=PROJECT_ROOT):
    now = utcnow()
    src = 'synthetic-lab'
    store = IntelligenceStore()
    fixture_id = 'synthetic:lab:fixture-001'
    url = 'https://example.org/dragonhydra-synthetic'
    evidence = {'synthetic':True,'purpose':'Controlled arithmetic and display demonstration','fixture_id':fixture_id}
    raw_hash = digest(encode(evidence))
    with sql_connection() as conn:
        store.append(conn,'sources',src,dict(evidence,name='DRAGONHYDRA synthetic generator',source_id=src),src,now)
        store.append(conn,'fixtures',fixture_id,dict(evidence,home_team='Synthetic Team A',away_team='Synthetic Team B',
                     source_id=src,event_at=None,observed_at=now,available_at=now,updated_at=now),src,now)
        for selection,price in (('HOME',2.0),('DRAW',3.5),('AWAY',4.0)):
            quote = OddsObservation(uuid4().hex,fixture_id,src,'SYNTHETIC — no bookmaker','h2h','h2h:full_time',
                    selection,None,price,probability(price),now,now,None,None,None,'UNKNOWN',url,raw_hash,1.0,'UNCONFIRMED',now,synthetic=True)
            payload = dict(asdict(quote),source_type='SYNTHETIC',retrieved_at=now,content_hash=raw_hash,
                           parser_version='synthetic/1.0',license_status='LOCAL_SYNTHETIC',terms_status='NOT_APPLICABLE',robots_status='NOT_APPLICABLE')
            store.append(conn,'markets',fixture_id+':h2h',{'fixture_id':fixture_id,'market_key':'h2h:full_time','synthetic':True},src,now)
            store.append(conn,'odds_observations',fixture_id+':'+selection,payload,src,now,
                         dedup_key=digest(encode([fixture_id,selection,price])))
        conn.commit()
    checkpoint(root,'synthetic-odds',evidence)


def build_summary(root=PROJECT_ROOT):
    summary = PresentationStore().cache(IntelligenceStore().summary())
    checkpoint(root,'presentation',summary)
    return summary


def main():
    if sys.version_info[:2] != (3,14):
        raise SystemExit('Python 3.14 required')
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('fetch-demo','process','synthetic-demo','summary'))
    args = parser.parse_args()
    try:
        if args.command == 'fetch-demo':
            print(json.dumps(asdict(capture())))
            build_summary()
        elif args.command == 'process':
            result = process_inbox()
            build_summary()
            print(json.dumps(result))
            if any(r['status']=='FAILED' for r in result):
                raise SystemExit(1)
        elif args.command == 'synthetic-demo':
            synthetic_odds()
            print('Synthetic odds stored and labelled.')
        else:
            result = build_summary()
            print(json.dumps({'counts':result['counts'],'built_at':result['built_at']}))
    except Exception as error:
        print(json.dumps({'status':'FAILED','reason':str(error) if isinstance(error,PipelineError) else type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
