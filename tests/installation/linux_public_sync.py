"""Bounded real public sync on the exact isolated R7 unit; no application edits."""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import stat
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT=Path(__file__).resolve().parents[2]
PREFIX=Path('/opt/dragonhydra/api');STATE=Path('/var/lib/dragonhydra-api')
UNIT='dragonhydra-api.service';BASE='http://127.0.0.1:55971';API='/dragon/api/v1'
VERSION='0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
EFFECTIVE='4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
ORIGIN='8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5'
PROVIDERS=('football-data-couk','statsbomb','cricsheet')
TERMINAL={'succeeded','failed','cancelled'}

def utc():return datetime.now(timezone.utc).isoformat()
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve()
    boundary=ROOT/'build/linux/native-kernel-20261031/public-sync-7'
    if platform.system()!='Linux' or os.getuid()!=0 or work!=boundary/'run' or work.exists():
        raise SystemExit('Native root, exact fresh public-sync-7/run evidence required.')
    acl=json.loads((boundary/'ACL-RESTRICTED.json').read_text())
    if not acl['restricted'] or acl['allowed_sid_count']!=3:
        raise SystemExit('Prepare and verify the Windows ACL on private-evidence first.')
    private=boundary/'private-evidence'
    if not private.is_dir() or (private/'core-before-public-sync.sqlite3').exists():
        raise SystemExit('Preserve previous private backups.')
    work.mkdir(parents=True)
    report={'schema_version':1,'started_at':utc(),'passed':False,'scope':'Actual authenticated API public HTTP synchronization on only owned native R7 test unit',
            'mode':'fresh_public_http','supported_api_body':{'mode':'fresh'},'checks':[],'providers':[], 'commands':[],
            'job_ids':[],'service_changes':[],'source_edits':False,'config_changes':False,'model_executed':False,
            'browser_or_connections_ui_tested':False,'public_metadata_modified':False,'harness_sha256':digest(__file__)}
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    token='';opener=build_opener(ProxyHandler({}));owned_jobs=set();cancelled=set()

    def redact(value):
        text=str(value)
        if token:text=text.replace(token,'[REDACTED]')
        return text
    def save():
        (work/'verification.json').write_text(redact(json.dumps(report,indent=2))+'\n')
    def check(name,**facts):
        report['checks'].append({'name':name,'passed':True,**facts});save()
        print(json.dumps({'passed':name,**facts}),flush=True)
    def run(name,argv,timeout=50):
        start=time.monotonic();result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        (work/(name+'.stdout.log')).write_text(redact(result.stdout));(work/(name+'.stderr.log')).write_text(redact(result.stderr))
        report['commands'].append({'name':name,'argv':argv,'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)})
        if result.returncode:raise RuntimeError(name+' failed: '+redact(result.stderr)[:500])
        return result.stdout.strip()
    def service(name):
        props=dict(line.split('=',1) for line in run(name,['systemctl','show',UNIT,'-p','ActiveState','-p','SubState','-p','MainPID','-p','FragmentPath','-p','ExecStart','-p','DynamicUser']).splitlines() if '=' in line)
        if props.get('FragmentPath')!='/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser')!='yes' or str(PREFIX/'bin/dragonhydra-server') not in props.get('ExecStart','') or '--state '+str(STATE) not in props.get('ExecStart',''):
            raise RuntimeError('Exact product unit ownership mismatch.')
        return props
    def request(path,method='GET',payload=None,expected=200,authenticate=True,timeout=8,idempotency=None):
        headers={'Content-Type':'application/json'}
        if authenticate:headers['Authorization']='Bearer '+token
        if idempotency:headers['Idempotency-Key']=idempotency
        data=json.dumps(payload).encode() if payload is not None else None
        try:response=opener.open(Request(BASE+API+path,data=data,method=method,headers=headers),timeout=timeout)
        except HTTPError as error:response=error
        with response:
            body=response.read(4*1024*1024)
            if response.status!=expected:raise RuntimeError(method+' '+path+' expectedHTTP'+str(expected)+' actualHTTP'+str(response.status))
            return json.loads(body) if response.headers.get_content_type()=='application/json' else body
    def ready(name,old_pid=None):
        nonlocal token
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            props=service(name+'-unit');pid=int(props.get('MainPID','0'))
            if props.get('ActiveState')=='active' and pid and pid!=old_pid:
                try:
                    endpoint=json.loads((STATE/'endpoint.json').read_text())
                    if endpoint.get('pid')!=pid or endpoint.get('url')!=BASE:raise RuntimeError('Expected same owned port55971.')
                    token=json.loads((STATE/'local-session.json').read_text())['token']
                    health=request('/health/ready',timeout=3)
                    if health['status']=='ready':return {'pid':pid,'url':BASE,'health':health}
                except (OSError,URLError,ValueError):pass
            time.sleep(.2)
        raise RuntimeError('Owned unit readiness deadline exceeded.')
    def database():
        return sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro',uri=True)
    def table_snapshot(db,names):
        values={}
        for name in names:
            if not re.fullmatch('[a-z_]+',name):raise RuntimeError('Unexpected owned table identifier')
            rows=db.execute('SELECT * FROM "'+name+'"').fetchall()
            payloads=sorted(encode(row) for row in rows)
            values[name]={'rows':len(rows),'sha256':hashlib.sha256(b'\n'.join(payloads)).hexdigest()}
        return values
    def snapshot():
        with closing(database()) as db:
            public=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            connectors=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'connector_%'")]
            values={'openfootball_tables':table_snapshot(db,public),'connector_tables':table_snapshot(db,connectors)}
            values['active_jobs']=db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running','interrupted')").fetchone()[0]
            values['periodic_schedules']=db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds>0').fetchone()[0]
        values['pairing_sha256']=hashlib.sha256(token.encode()).hexdigest()
        values['protected_files']={name:{'sha256':digest(path),'mode':oct(stat.S_IMODE(path.stat().st_mode))} for name,path in
            [('session',STATE/'local-session.json'),('managed_port',STATE/'managed-port.json'),('environment',Path('/etc/dragonhydra/api.env'))]}
        values['football_matches']=request('/matches?limit=1')['total']
        values['connections']={item['id']:{'status':item['status'],'record_count':item['record_count'],'last_successful_retrieval':item.get('last_successful_retrieval')} for item in request('/connections')['items']}
        return values
    def cancel_once(ident):
        if ident in cancelled:return
        cancelled.add(ident);request('/jobs/'+ident+'/cancel','POST',{})
        report.setdefault('cancellation_requests',[]).append(ident);save()
    def execute_sync(provider):
        entry={'provider':provider,'started_at':utc(),'states':[],'passed':False};report['providers'].append(entry);save()
        submitted=request('/connections/'+provider+'/sync','POST',{'mode':'fresh'},expected=202,idempotency='native-r7-public-'+provider+'-'+str(time.time_ns()))
        ident=submitted['id'];owned_jobs.add(ident);report['job_ids'].append(ident);entry['job_id']=ident;entry['submission_http_status']=202
        deadline=time.monotonic()+135;last=None;terminal=None
        while time.monotonic()<deadline:
            job=request('/jobs/'+ident)
            state={key:job.get(key) for key in ('status','progress','attempts','error')}
            if state!=last:
                entry['states'].append({'observed_at':utc(),**state});last=state;save()
                print(json.dumps({'provider':provider,'job_id':ident,**state}),flush=True)
            if job['status'] in TERMINAL:terminal=job;break
            time.sleep(.5)
        if terminal is None:
            cancel_once(ident);end=time.monotonic()+15
            while time.monotonic()<end:
                job=request('/jobs/'+ident)
                if job['status'] in TERMINAL:terminal=job;break
                time.sleep(.5)
        if terminal is None:
            entry.update(error={'code':'CANCELLATION_PENDING','message':'Exact test job cancellation did not settle; no next sync submitted.'},finished_at=utc())
            save();raise RuntimeError('Owned job cancellation still pending: '+ident)
        entry['terminal_status']=terminal['status'];entry['finished_at']=utc()
        if terminal['status']!='succeeded':
            entry['error']=terminal.get('error');entry['cached_health']=request('/health/ready')['status'];save();return
        result=terminal['result'];entry['result']=result
        if not result.get('retrieved') or not result.get('endpoint_reachable') or result.get('authentication')!='public' or result.get('normalized_rows',0)<=0:
            raise RuntimeError('Successful job lacks actual public retrieval/normalization proof.')
        receipts=[]
        with closing(database()) as db:
            db.row_factory=sqlite3.Row
            for acquisition in result['acquisitions']:
                row=db.execute('SELECT * FROM connector_acquisitions WHERE id=? AND provider=?',(acquisition['id'],provider)).fetchone()
                if row is None:raise RuntimeError('Committed acquisition receipt missing')
                raw=STATE/'raw/connectors'/row['raw_reference']
                if not raw.resolve().is_relative_to((STATE/'raw/connectors').resolve()) or not raw.is_file():raise RuntimeError('Unsafe or missing raw evidence')
                if raw.stat().st_size!=row['bytes'] or digest(raw)!=row['sha256'] or row['sha256']!=acquisition['sha256'] or row['http_status']!=200:
                    raise RuntimeError('Full raw bytes do not match committed public acquisition')
                metadata=request('/connections/'+provider+'/acquisitions/'+row['id'])
                if metadata['id']!=row['id'] or metadata['sha256']!=row['sha256'] or metadata['captured_at']!=row['captured_at'] or 'raw_reference' in metadata:
                    raise RuntimeError('Public receipt API differs from exact retained acquisition')
                clock=datetime.fromisoformat(row['captured_at'].replace('Z','+00:00'))
                if clock.tzinfo is None or clock.utcoffset().total_seconds()!=0 or clock<datetime.fromisoformat(entry['started_at']):
                    raise RuntimeError('Receipt is not a fresh UTC capture from this operation')
                receipts.append(metadata)
        entry['committed_acquisitions']=receipts
        current={item['id']:item for item in request('/connections')['items']}[provider]
        entry['connection_after']={key:current.get(key) for key in ('id','status','record_count','last_successful_retrieval','last_retrieval_count','last_import','live','quarantined_count','identity_review_count')}
        if current['status']!='working' or current['record_count']!=result['record_count'] or not current['last_successful_retrieval']:
            raise RuntimeError('Connections API does not reflect committed real sync')
        page=request('/connections/'+provider+'/records?limit=1')
        if page['total']!=result['record_count'] or not page['items']:raise RuntimeError('Imported records unavailable through provider API')
        entry['first_observation_id']=page['items'][0]['id'];entry['first_record_sport']=page['items'][0]['sport']
        if provider in ('football-data-couk','statsbomb'):
            matches=request('/matches?provider='+provider+'&limit=1')
            if not matches['items']:raise RuntimeError('Football source has no canonical visible match')
            match=matches['items'][0];detail=request('/matches/'+match['id']);team=request('/teams/'+match['home']['id']);evidence=request('/evidence/'+match['evidence_id'])
            if detail['id']!=match['id'] or team['name']!=match['home']['name'] or evidence.get('evidence_id')!=match['evidence_id']:
                raise RuntimeError('Same-source match/team/evidence identity mismatch')
            entry['football_navigation']={'match_id':match['id'],'home':match['home']['name'],'away':match['away']['name'],'status':match['status'],'team_id':team['id'],'evidence_id':match['evidence_id'],'source_id':match['source_id']}
            quotes=request('/matches/'+match['id']+'/odds')
            if any(item['match_id']!=match['id'] or item['source_id']!=provider for item in quotes['items']):raise RuntimeError('Incompatible quote linked to selected match')
            entry['odds']={'count':len(quotes['items']),'axis':quotes['axis'],'reason':quotes.get('reason')}
            if quotes['items']:
                for item in quotes['items']:
                    if not item.get('acquisition_id') or item['provenance_status']!='bound':raise RuntimeError('Archive quote does not bind exact retained receipt')
                entry['odds']['exact_acquisition_bindings_verified']=True
        entry['passed']=True;save()
        check('Fresh '+provider+' retrieval, normalization, provenance and API status',retrieved_rows=result['retrieved_rows'],normalized_rows=result['normalized_rows'],inserted=result.get('inserted'),quarantined=result.get('quarantined'),stored=result['record_count'],acquisitions=len(receipts))

    try:
        identity=json.loads((PREFIX/'BUILD-IDENTITY.json').read_text());module=json.loads((PREFIX/'site-packages/dragonhydra/build_info.json').read_text())
        if identity['debian_version']!=VERSION or identity['source_content_sha256']!=EFFECTIVE or identity['application_snapshot_sha256']!=ORIGIN or module['source_content_sha256']!=EFFECTIVE:
            raise RuntimeError('Installed R7 source identity mismatch')
        if run('owned-package-version',['dpkg-query','-W','-f=${Version}','dragonhydra-api'])!=VERSION:raise RuntimeError('Native package version mismatch')
        manifest=json.loads((ROOT/'dist/linux/native-kernel-20261031/r7/PAYLOAD-MANIFEST.json').read_text())
        for item in manifest['files']:
            path=Path('/')/item['path']
            if path.is_symlink() or path.stat().st_size!=item['bytes'] or digest(path)!=item['sha256']:raise RuntimeError('Installed R7 payload drift: '+item['path'])
        first=ready('initial');report['initial_ready']=first
        request('/matches?limit=1',authenticate=False,expected=401)
        before=snapshot();report['before']=before
        if before['football_matches']!=760 or before['active_jobs'] or before['periodic_schedules'] or any(before['connections'][provider]['record_count'] for provider in PROVIDERS):
            raise RuntimeError('Expected760-record pristine-provider test baseline not established; no sync started')
        if any(value['mode']!='0o600' for value in before['protected_files'].values()):raise RuntimeError('Protected files are not native0600')
        backup=private/'core-before-public-sync.sqlite3'
        with closing(database()) as db, closing(sqlite3.connect(backup)) as destination:db.backup(destination)
        report['consistent_backup']={'path':'../private-evidence/core-before-public-sync.sqlite3','sha256':digest(backup),'windows_acl_restricted':True,'session_token_copied':False}
        check('Exact R7 owned service760-record baseline and protected consistent backup verified',payload_files=len(manifest['files']),port=55971)
        for provider in PROVIDERS:execute_sync(provider)
        after=snapshot();report['after_sync']=after
        if after['openfootball_tables']!=before['openfootball_tables'] or after['protected_files']!=before['protected_files'] or after['pairing_sha256']!=before['pairing_sha256']:
            raise RuntimeError('Original OpenFootball records/evidence or protected configuration changed')
        if after['active_jobs'] or after['periodic_schedules']:raise RuntimeError('Pending work or periodic sync remains after bounded test')
        check('Original760-source tables/evidence/pairing/config retained; no queued work or schedules',football_matches=after['football_matches'])
        report['all_public_syncs_succeeded']=all(item['passed'] for item in report['providers'])
        if report['all_public_syncs_succeeded']:
            previous=service('before-controlled-restart')
            run('restart-only-owned-r7',['systemctl','restart',UNIT]);report['service_changes'].append('One controlled restart of '+UNIT)
            final=ready('after-controlled-restart',int(previous['MainPID']));persisted=snapshot()
            if persisted!=after:raise RuntimeError('Source records/receipts/config/pairing changed after restart')
            report['after_restart']=persisted;report['final_ready']=final
            check('Freshly imported records and original data persist after one same-port controlled restart',football_matches=persisted['football_matches'],port=55971)
        else:report['final_ready']=ready('partial-cached-browsing')
        report['passed']=report['all_public_syncs_succeeded']
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':redact(error)}
    finally:
        pending=[]
        for ident in sorted(owned_jobs):
            try:
                job=request('/jobs/'+ident)
                if job['status'] not in TERMINAL:cancel_once(ident);pending.append(ident)
            except Exception as error:report.setdefault('cleanup_errors',[]).append(redact(error))
        report['pending_owned_jobs']=pending
        if pending:report['passed']=False
        try:report['last_observed_service']=service('final-owned-service')
        except Exception as error:report['final_service_error']=redact(error);report['passed']=False
        report['finished_at']=utc();report['observed_not_continuous_hosting']=True;save()
        print(json.dumps({'passed':report['passed'],'providers':[{'provider':item['provider'],'passed':item['passed'],'status':item.get('terminal_status'),'error':item.get('error'),'result':{key:item.get('result',{}).get(key) for key in ('retrieved_rows','normalized_rows','inserted','quarantined','record_count')}} for item in report['providers']],
                          'error':report.get('error'),'pending_owned_jobs':pending,'evidence':str(work/'verification.json')},indent=2),flush=True)
    return 0 if report['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
