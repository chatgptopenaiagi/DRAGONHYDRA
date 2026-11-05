"""Explicit one-phase installed dev7 acceptance; no installer/service/SQL controls.

Root supplies immutable --bindings + SHA256 only after source/package/profile
freeze. Binding schema core-next.dev7-service-bindings/1 names source_commit,
version, build_id, installation_id, ports, profile{path,sha256}, setup{path,
sha256}, operation_root, target_match_id, profile_helper{path,sha256},
support_sha256, sql_provision{path,sha256}, sql{server,database,database_user,service_sid}.
The SQL provisioner/Windows phase controller are separate reviewed operations.

Phases are never looped: read-fresh, initialize, forecast, publication-denied,
publish, backup-readback, restart-readback, repair-readback,
uninstalled-readback, reinstall-readback, final-uninstalled-readback.
The denied publication is submitted ONCE, never retried. Root restores its
one INSERT grant in finally and supplies a hash-bound restoration/zero-delta
receipt before the later, explicitly distinct publish job. No SQL text/proxy,
provider call, local AI, native GUI, elevation or service mutation exists here.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import traceback
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
GIT=r'C:\Program Files\Git\cmd\git.exe'
LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
ORIGINAL_SUPPORT='47d5ffc472bbb0675ab8942c77fccb14e9a780e8f40acff2e397fe5e1c197f0b'
PHASES={'read-fresh':('fresh',None),'initialize':('workflow','read-fresh'),
    'forecast':('workflow','initialize'),'publication-denied':('workflow','forecast'),
    'publish':('workflow','publication-denied'),'backup-readback':('readback','publish'),
    'restart-readback':('readback','backup-readback'),'repair-readback':('readback','restart-readback'),
    'uninstalled-readback':('uninstalled','repair-readback'),'reinstall-readback':('readback','uninstalled-readback'),
    'final-uninstalled-readback':('uninstalled','reinstall-readback')}

class GateError(Exception):pass
def need(value,code):
    if not value:raise GateError(code)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def ordinary(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.exists() or part.is_symlink():
            need(not part.is_symlink() and not getattr(part.lstat(),'st_file_attributes',0)&0x400,'LINKED_ACCEPTANCE_PATH')
    return path
def load(path):return json.loads(ordinary(path).read_text(encoding='utf-8-sig'))
def bound(spec):
    path=ordinary(spec['path']);need(path.is_file() and digest(path)==spec['sha256'],'INPUT_HASH_MISMATCH');return path
def source_bytes(source,relative):
    return subprocess.check_output([GIT,'--no-optional-locks','-C',str(ROOT),'show',source+':'+relative],stderr=subprocess.DEVNULL,timeout=15)

def validate_release_identity(source,version):
    # Validate the object name before passing it to Git. Release acceptance uses
    # the immutable matrix of the bound source, including historical candidates.
    need(isinstance(source,str) and re.fullmatch('[a-f0-9]{40}',source),'RELEASE_IDENTITY_REQUIRED')
    try:matrix=json.loads(source_bytes(source,'packaging/release/version.json'))
    except (UnicodeDecodeError,json.JSONDecodeError):raise GateError('FROZEN_RELEASE_MATRIX_INVALID') from None
    need(isinstance(matrix,dict) and isinstance(matrix.get('product_version'),str)
         and bool(matrix['product_version']) and version==matrix['product_version'],'RELEASE_VERSION_NOT_FROZEN_SOURCE')

def authorize(phase,method,path,target,approved_jobs):
    reads={'/health/ready','/system','/modules','/modules?scope=all','/research/storage',
           '/matches/'+target+'/cognition-history','/matches/'+target+'/research/archives'}
    if method=='GET':
        if path in reads or re.fullmatch(r'/matches\?limit=200&offset=[0-9]{1,5}',path):return
        m=re.fullmatch(r'/(?:jobs/([a-f0-9]{32})|exports/([a-f0-9]{32})/download)',path)
        if m and next(x for x in m.groups() if x) in approved_jobs:return
        if re.fullmatch(r'/research/archives/[a-f0-9]{64}(?:/match)?',path):return
    actions={'initialize':{'/research/storage/initialize'},'forecast':{'/matches/'+target+'/forecasts','/matches/'+target+'/evaluations'},
             'publication-denied':{'/matches/'+target+'/research/archives'},'publish':{'/matches/'+target+'/research/archives','/exports'}}
    need(method=='POST' and path in actions.get(phase,set()),'API_OPERATION_OUTSIDE_PHASE_ALLOWLIST')

def validate_bindings(path,expected):
    path=ordinary(path);need(path.is_file() and digest(path)==expected,'BINDINGS_HASH_MISMATCH');b=load(path)
    need(b.get('schema_version')=='core-next.dev7-service-bindings/1','BINDINGS_SCHEMA_MISMATCH')
    validate_release_identity(b.get('source_commit'),b.get('version'))
    identity=b.get('installation_id','');need(re.fullmatch('core-next-[a-f0-9]{32}',identity),'OWNED_NEW_PROFILE_REQUIRED')
    need(identity not in {'core-next-b447d99ab9524197af09c235077685de','core-next-7ac520727b85456cac4a3a92a8dd62da'},'HISTORICAL_PROFILE_FORBIDDEN')
    ports=b.get('ports',{});need(set(ports)=={'api','web','database'} and all(type(v) is int and 1024<=v<=65535 and not 18740<=v<=18751 for v in ports.values()) and len(set(ports.values()))==3,'EXCLUSIVE_PORTS_REQUIRED')
    operation=ordinary(b['operation_root']);need(operation.is_relative_to(LAB) and operation!=LAB and operation.is_dir(),'PRIVATE_OPERATION_REQUIRED')
    profile_path=bound(b['profile']);profile=load(profile_path)
    need(profile_path==LAB/'profiles'/identity/'installation-profile.json','PROFILE_PATH_MISMATCH')
    for key in ('installation_id','source_commit','version','build_id','ports'):need(profile.get(key)==b[key],'PROFILE_BINDING_MISMATCH')
    setup=bound(b['setup']);need(setup.is_relative_to(LAB/'dist') and setup.suffix.lower()=='.exe','OWNED_SETUP_REQUIRED')
    for key in ('profile_helper','sql_provision'):bound(b[key])
    need(source_bytes(b['source_commit'],'packaging/windows/workstation/CoreNextProfile.ps1')==Path(b['profile_helper']['path']).read_bytes(),'PROFILE_HELPER_NOT_FROZEN_SOURCE')
    support=ROOT/'tests/installation/disposable_workstation_support.py'
    need(digest(support)==b['support_sha256'],'SUPPORT_HASH_MISMATCH')
    need(source_bytes(b['source_commit'],'tests/installation/dev7_service_acceptance.py')==Path(__file__).read_bytes(),'ADAPTER_NOT_FROZEN_SOURCE')
    need(source_bytes(b['source_commit'],'tests/installation/disposable_workstation_support.py')==support.read_bytes(),'SUPPORT_NOT_FROZEN_SOURCE')
    provision=load(b['sql_provision']['path'])
    need(provision.get('schema_version')=='dragonhydra.core-next.sql-provisioning/1'
         and provision.get('passed') is True and provision.get('installation_id')==identity
         and provision.get('source_commit')==b['source_commit'] and provision.get('service_name')==profile['service_name']
         and provision.get('database')==b['sql']['database'] and provision.get('server')==b['sql']['server']
         and provision.get('service_sid')==b['sql']['service_sid'],'SQL_PROVISION_BINDING_MISMATCH')
    need(re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}',b['sql']['database']) and isinstance(b['sql']['database_user'],str) and b['sql']['database_user'],'DEDICATED_SQL_IDENTITY_REQUIRED')
    need(re.fullmatch('[a-f0-9]{64}',b['target_match_id']),'RETAINED_TARGET_REQUIRED')
    return b,profile

def specialize(module,name,old,new):
    """Change one reviewed literal seam, with no string-built executable code."""
    tree=ast.parse(Path(module.__file__).read_bytes());node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    matches=[n for n in ast.walk(node) if isinstance(n,ast.Constant) and n.value==old]
    need(len(matches)==1,'AUDITED_SUPPORT_LITERAL_CHANGED');matches[0].value=new
    namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),module.__file__,'exec'),module.__dict__,namespace)
    return namespace[name]

def support_module(b,profile,args):
    path=ROOT/'tests/installation/disposable_workstation_support.py';raw=path.read_bytes().decode('utf-8')
    header='\n'.join(raw.splitlines()[:2])+'\n';body=raw[len(header):].replace("if __name__=='__main__':raise SystemExit('SUPPORT_MODULE_ONLY_USE_DEV7_SERVICE_ACCEPTANCE')","if __name__=='__main__':raise SystemExit(main())")
    need(hashlib.sha256(body.encode()).hexdigest()==ORIGINAL_SUPPORT,'VENDORED_SUPPORT_PROVENANCE_MISMATCH')
    spec=importlib.util.spec_from_file_location('dev7_frozen_disposable_support',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.FRESH=b['installation_id'];m.SOURCE=b['source_commit'];m.VERSION=b['version'];m.SETUP=b['setup']['sha256'];m.TARGET=b['target_match_id']
    m.KEY='dev7-'+hashlib.sha256(canonical([b['installation_id'],b['source_commit'],str(b['operation_root'])])).hexdigest()[:40]
    m.PORTS={m.FRESH:b['ports']};m.PROFILE=Path(b['profile']['path']);m.EXPECTED_SETUP=Path(b['setup']['path']);m.OPERATION=Path(b['operation_root'])
    m.SCHEMA='dev7.disposable-acceptance/1';m.PHASES=PHASES;m.PROFILE_HELPER_SHA256=b['profile_helper']['sha256']
    m.guard_profile=specialize(m,'guard_profile','package-dev5-r1',b['build_id'])
    m.Acceptance.ownership=specialize(m,'ownership','C:/xampp/DRAGONHYDRA-CORE-NEXT/packaging/windows/workstation/CoreNextProfile.ps1',str(Path(b['profile_helper']['path'])))
    reference=m.guard_reference
    def predecessor(doc,mode,phase):
        reference(doc,mode,phase)
        if doc:need(doc.get('adapter_sha256')==digest(Path(__file__)) and doc.get('bindings_sha256')==args.bindings_sha256,'PREDECESSOR_ADAPTER_OR_BINDING_CHANGED')
    m.guard_reference=predecessor
    return m

def job_delta(before,after,approved):
    """Exact append-only jobs/events outside the separately audited forecast window."""
    snapshots=[]
    for path in (before,after):
        with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.row_factory=sqlite3.Row
            snapshots.append({name:{row[key]:dict(row) for row in db.execute('SELECT * FROM '+name+' ORDER BY '+key)}
                              for name,key in [('product_jobs','id'),('product_updates','seq'),('sqlite_sequence','name')]})
    a,z=snapshots
    for table in ('product_jobs','product_updates'):
        need(all(z[table].get(k)==v for k,v in a[table].items()),'PREEXISTING_JOB_OR_EVENT_CHANGED')
    new=set(z['product_jobs'])-set(a['product_jobs']);need(new==set(approved),'UNAPPROVED_JOB_DELTA')
    events={k:v for k,v in z['product_updates'].items() if k not in a['product_updates']};seen={k:[] for k in new}
    for event in events.values():
        payload=json.loads(event['payload']);identity=payload.get('id') if event['topic']=='job' else payload.get('job_id')
        need(identity in new,'UNAPPROVED_EVENT_DELTA')
        if event['topic']=='job':need(set(payload)=={'id','status'},'UNEXPECTED_JOB_EVENT');seen[identity].append(payload['status'])
        else:need(event['topic']=='data' and payload=={'job_id':identity,'kind':z['product_jobs'][identity]['kind']},'UNEXPECTED_DATA_EVENT');seen[identity].append('data')
    for identity,status in approved.items():
        row=z['product_jobs'][identity];need(row['status']==status and row['attempts']==1,'JOB_RETRY_OR_TERMINAL_MISMATCH')
        need(seen[identity]==['queued','running',status]+(['data'] if status=='succeeded' else []),'JOB_EVENT_TRANSITION_MISMATCH')
    first=max(a['product_updates'],default=0)+1
    need(sorted(events)==list(range(first,first+len(events))),'EVENT_SEQUENCE_DELTA_MISMATCH')
    need({k:v for k,v in a['sqlite_sequence'].items() if k!='product_updates'}=={k:v for k,v in z['sqlite_sequence'].items() if k!='product_updates'},'OTHER_SEQUENCE_CHANGED')
    for snapshot in (a,z):
        need(snapshot['sqlite_sequence'].get('product_updates',{}).get('seq')==max(snapshot['product_updates'],default=0),'UPDATE_SEQUENCE_MAX_MISMATCH')
    return {'approved_jobs':len(new),'new_events':len(events),'old_jobs_events_preserved':True}

def make_acceptance(m,b,profile,args):
    class Acceptance(m.Acceptance):
        def __init__(self,original):
            self.approved={};self.snapshots={};self.extra={};self.sql_work={};self.workflow={}
            super().__init__(original)
            if self.reference:
                self.workflow=self.reference.get('workflow',{})
                self.sql_work=self.reference.get('sql_work',{})
                self.approved=dict(self.reference.get('approved_jobs',{}))
        def save(self,passed=False):
            super().save(passed)
            path=self.output/'verification.json';report=m.read(path)
            report.update(adapter_sha256=digest(Path(__file__)),bindings_sha256=args.bindings_sha256,sql_work=self.sql_work,approved_jobs=self.approved,
                extra=self.extra,service_sql_postwrite_rollback='Only the separately hash-bound root permission-fault zero-delta proof establishes this; stale409 is not substituted.')
            temporary=self.output/('adapter.'+m.uuid.uuid4().hex+'.tmp')
            with temporary.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
            temporary.replace(path)
        def database(self,label):
            result=super().database(label);self.snapshots[label]=self.private/(label+'.sqlite3');return result
        def api_request(self,method,path,body=None,key=None,download=False):
            authorize(args.phase,method,path,m.TARGET,self.approved)
            if method=='POST':
                expected={
                    '/research/storage/initialize':({},m.KEY+'-initialize'),
                    '/matches/'+m.TARGET+'/forecasts':({},m.KEY),
                    '/matches/'+m.TARGET+'/evaluations':({},m.KEY+'-evaluation'),
                    '/matches/'+m.TARGET+'/research/archives':({'forecast_run_id':self.workflow.get('forecast_job_id')},m.KEY+'-'+args.phase)}
                if path=='/exports':need(body in [{'match_id':m.TARGET,'format':fmt} for fmt in ['json','csv','xlsx']] and key==m.KEY+'-export-'+body['format'],'EXPORT_PAYLOAD_KEY_MISMATCH')
                else:need((body,key)==expected[path],'ACTION_PAYLOAD_KEY_MISMATCH')
                need(self.predecessor_verified,'CLASS_C_PREDECESSOR_REQUIRED')
            else:need(body is None and key is None,'GET_WITH_ACTION_PAYLOAD')
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/json'}
            if body is not None:headers['Content-Type']='application/json'
            if key:headers['Idempotency-Key']=key
            self.requests.append({'method':method,'path':path})
            try:
                with self.api_opener.open(Request(self.api+path,data=canonical(body) if body is not None else None,headers=headers,method=method),timeout=20) as response:
                    code=response.status;raw=response.read(8*1024*1024+1)
            except HTTPError as error:code=error.code;raw=error.read(1024*1024)
            need(code==(202 if method=='POST' else 200) and len(raw)<=8*1024*1024,'API_RESPONSE_STATUS_OR_BOUND')
            self.responses.append(raw)
            if download:return raw
            value=json.loads(raw)
            if method=='POST':need(re.fullmatch('[a-f0-9]{32}',str(value.get('id',''))),'JOB_ID_INVALID');self.approved.setdefault(value['id'],'pending')
            return value
        def terminal(self,item,expected='succeeded'):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                job=self.api_get('/jobs/'+item['id'])
                if job['status'] in {'succeeded','failed','cancelled','interrupted'}:
                    need(job['status']==expected and job.get('attempts')==1,'EXPLICIT_JOB_TERMINAL_OR_ATTEMPTS_MISMATCH');self.approved[job['id']]=expected;return job
                time.sleep(.2)
            raise GateError('EXPLICIT_JOB_TIMEOUT_NO_RETRY')
        def submit(self,path,body,key):
            job=self.terminal(self.api_request('POST',path,body,key));replay=self.api_request('POST',path,body,key)
            need(replay['id']==job['id'] and replay['result']==job['result'],'DUPLICATE_JOB_OR_RESULT_CHANGED');return job
        def sql_health(self):
            value=self.api_get('/research/storage');health=value.get('research',{});identity=health.get('connection_identity',{})
            need(value.get('canonical_backend')=='sqlite' and value.get('installation',{}).get('installation_id')==m.FRESH
                 and health.get('ready') is True and health.get('schema_version')==1 and health.get('provider')=='sqlserver'
                 and health.get('server')==b['sql']['server'],'SERVICE_SQL_HEALTH_UNVERIFIED')
            need(identity.get('database')==b['sql']['database'] and identity.get('database_user')==b['sql']['database_user']
                 and identity.get('auth_scheme','').upper() in {'NTLM','KERBEROS'} and all(isinstance(identity.get(k),str) and identity[k] for k in ['login','database_user','database','net_transport','auth_scheme']),'ACTUAL_SERVICE_SQL_IDENTITY_MISMATCH')
            self.extra['sql_connection_identity']=identity;return health
        def permission_proof(self,mode):
            need(args.permission_receipt and args.permission_sha256,'EXPLICIT_PERMISSION_RECEIPT_REQUIRED')
            proof=load(bound({'path':args.permission_receipt,'sha256':args.permission_sha256}))
            need(proof.get('schema_version')=='core-next.dev7-sql-permission-proof/1' and proof.get('passed') is True
                 and proof.get('source_commit')==m.SOURCE and proof.get('installation_id')==m.FRESH and proof.get('database')==b['sql']['database']
                 and proof.get('service_sid')==b['sql']['service_sid'] and proof.get('permission')=='INSERT'
                 and proof.get('object')=='dbo.dh_research_inputs' and proof.get('mode')==mode and proof.get('only_selected_permission_changed') is True,'PERMISSION_FAULT_BINDING_MISMATCH')
            if mode=='restored':need(proof.get('failed_job_id')==self.sql_work.get('failed_publication_job_id') and proof.get('all_sql_rows_unchanged') is True,'POSTWRITE_ROLLBACK_PROOF_REQUIRED')
            self.extra['permission_proof']={'path':str(args.permission_receipt),'sha256':args.permission_sha256,'mode':mode}
        def workflow_action(self):
            if args.phase=='initialize':
                job=self.submit('/research/storage/initialize',{},m.KEY+'-initialize');self.sql_work['initialize_job_id']=job['id']
            elif args.phase=='forecast':
                forecast=self.submit('/matches/'+m.TARGET+'/forecasts',{},m.KEY);result=forecast['result']
                need(result.get('available') is True and result.get('status')=='persisted' and len(result.get('model_runs',[]))==5 and len(result.get('predictions',[]))==5,'REAL_FORECAST_NOT_PERSISTED')
                need(all(x['parameters']['workflow']['build']['source_sha']==m.SOURCE and x['parameters']['workflow']['match_id']==m.TARGET for x in result['model_runs']),'FORECAST_PROVENANCE_MISMATCH')
                evaluation=self.submit('/matches/'+m.TARGET+'/evaluations',{},m.KEY+'-evaluation')
                need(evaluation['result'].get('status')=='pending' and evaluation['result'].get('available') is False and evaluation['result'].get('reason')=='LATER_RETAINED_OUTCOME_UNAVAILABLE','EVALUATION_NOT_HONESTLY_PENDING')
                history=self.api_get('/matches/'+m.TARGET+'/cognition-history')
                self.workflow={'match_id':m.TARGET,'forecast_job_id':forecast['id'],'evaluation_job_id':evaluation['id'],'forecast_key':m.KEY,
                    'record_ids':{k:[x['record_id'] for x in v] for k,v in history['records'].items()},'history_records_sha256':m.sha(canonical(history['records'])),'counts':history['counts']}
            elif args.phase=='publication-denied':
                self.permission_proof('revoked')
                # Exactly one submission. A failed write never enters submit()/duplicate logic.
                job=self.terminal(self.api_request('POST','/matches/'+m.TARGET+'/research/archives',{'forecast_run_id':self.workflow['forecast_job_id']},m.KEY+'-publication-denied'),'failed')
                need(job.get('error',{}).get('sqlstate')=='42000' and job['error'].get('uncertain_write') is False,'EXPECTED_SQL_PERMISSION_ROLLBACK_NOT_CONFIRMED')
                self.sql_work['failed_publication_job_id']=job['id'];self.extra['failed_job_no_retry']=True
            elif args.phase=='publish':
                self.permission_proof('restored')
                job=self.submit('/matches/'+m.TARGET+'/research/archives',{'forecast_run_id':self.workflow['forecast_job_id']},m.KEY+'-publish')
                self.sql_work.update(archive_job_id=job['id'],archive_id=job['result']['archive_id'])
                archive=self.api_get('/research/archives/'+self.sql_work['archive_id'])
                need(archive['archive']['forecast_run_id']==self.workflow['forecast_job_id'] and archive['archive']['source_build']['source_sha']==m.SOURCE,'PUBLISHED_ARCHIVE_PROVENANCE_MISMATCH')
                self.sql_work['archive_sha256']=m.sha(canonical(archive));self.sql_work['exports']={}
                for fmt in ['json','csv','xlsx']:
                    export=self.submit('/exports',{'match_id':m.TARGET,'format':fmt},m.KEY+'-export-'+fmt)
                    raw=self.api_request('GET','/exports/'+export['id']+'/download',download=True)
                    if fmt=='json':need(json.loads(raw)['match']['id']==m.TARGET,'JSON_EXPORT_INVALID')
                    elif fmt=='csv':need(list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))[0]['id']==m.TARGET,'CSV_EXPORT_INVALID')
                    else:
                        with ZipFile(io.BytesIO(raw)) as z:need(z.testzip() is None and m.TARGET.encode() in z.read('xl/worksheets/sheet1.xml'),'XLSX_EXPORT_INVALID')
                    target=self.private/(export['id']+'.'+fmt)
                    with target.open('xb') as f:f.write(raw)
                    self.sql_work['exports'][fmt]={'job_id':export['id'],'bytes':len(raw),'sha256':m.sha(raw)}
        def persisted_readback(self):
            if self.workflow:
                history=self.api_get('/matches/'+m.TARGET+'/cognition-history');need(m.sha(canonical(history['records']))==self.workflow['history_records_sha256'],'PERSISTED_COGNITIVE_HISTORY_CHANGED')
            for identity,status in self.approved.items():need(self.api_get('/jobs/'+identity)['status']==status,'PERSISTED_JOB_STATUS_CHANGED')
            if self.sql_work.get('archive_id'):
                archive=self.api_get('/research/archives/'+self.sql_work['archive_id']);need(m.sha(canonical(archive))==self.sql_work['archive_sha256'],'PERSISTED_SQL_ARCHIVE_CHANGED')
                for item in self.sql_work['exports'].values():need(m.sha(self.api_request('GET','/exports/'+item['job_id']+'/download',download=True))==item['sha256'],'PERSISTED_EXPORT_CHANGED')
        def run(self):
            if self.args.uninstalled:return super().run()
            self.bind();before=self.database('before-reads');rows=self.matches();ids=sorted([x['id'],x['version']] for x in rows)
            if self.reference:need(dict(before,match_id_versions=ids)==self.reference['snapshot'],'PREDECESSOR_STATE_CHANGED_NO_RETRY')
            presentation=self.presentation();self.sql_health();engines=self.api_get('/modules');all_=self.wait_service_identity(self.api_get('/modules?scope=all'))
            need(len(engines['items'])==6 and all_['inventory']=={'engines':6,'supporting':12,'total':18} and len(all_['items'])==18,'REGISTRY_INVENTORY_MISMATCH')
            self.check('installed_service_sql_identity_canonical_760_and_registry',retained=len(rows),inventory=all_['inventory'])
            prior_approved=dict(self.approved)
            if args.phase in {'initialize','forecast','publication-denied','publish'}:
                target=next((x for x in rows if x['id']==m.TARGET),None);need(target is not None and target['status']=='scheduled','REAL_RETAINED_FUTURE_TARGET_REQUIRED')
                self.stage='explicit_'+args.phase;self.workflow_action()
            else:self.persisted_readback()
            self.joomla(rows[0],{x['id'] for x in all_['items']});self.joomla_presentation=self.presentation()
            need(self.joomla_presentation==presentation,'JOOMLA_PRESENTATION_CHANGED')
            self.snapshot=self.database('after-reads');self.snapshot['match_id_versions']=ids
            if args.phase=='forecast':
                auditor=ROOT/'tests/installation/workflow_preservation.py'
                need(auditor.read_bytes()==source_bytes(m.SOURCE,'tests/installation/workflow_preservation.py'),'WORKFLOW_AUDITOR_NOT_FROZEN_SOURCE')
                spec=importlib.util.spec_from_file_location('frozen_workflow_preservation',auditor);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
                market=ast.parse(source_bytes(m.SOURCE,'src/dragonhydra/market_store.py'));memory=ast.parse(source_bytes(m.SOURCE,'src/dragonhydra/cognition/memory.py'))
                scripts=[n.args[0].value for n in ast.walk(market) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='executescript' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str) and 'CREATE TABLE IF NOT EXISTS acquisitions' in n.args[0].value]
                need(len(scripts)==1,'INDEPENDENT_MARKET_SCHEMA_REQUIRED')
                cognitive=next(n.value.value for n in memory.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMA_SQL' for t in n.targets))
                proof=audit.audit_workflow_preservation(self.snapshots['before-reads'],self.snapshots['after-reads'],approved_job_ids={k:self.workflow[k+'_job_id'] for k in ['forecast','evaluation']},approved_cognitive_ids=[x for values in self.workflow['record_ids'].values() for x in values],expected_schema=audit.canonical_schema_from_sql(scripts[0],cognitive))
                need(proof['passed'],'CORRECTED_FORECAST_PRESERVATION_FAILED');self.extra['workflow_preservation']=proof
                need(before['configuration_fingerprints']==self.snapshot['configuration_fingerprints'],'WORKFLOW_PRIVATE_CONFIGURATION_CHANGED')
            elif args.phase in {'initialize','publication-denied','publish'}:
                need(before['schema_objects']==self.snapshot['schema_objects'] and before['configuration_fingerprints']==self.snapshot['configuration_fingerprints'],'NONFORECAST_SCHEMA_OR_CONFIGURATION_CHANGED')
                need(all(before['domain_tables'].get(k)==self.snapshot['domain_tables'].get(k) for k in before['domain_tables'].keys()|self.snapshot['domain_tables'].keys() if k not in {'product_jobs','product_updates','sqlite_sequence'}),'NONFORECAST_DOMAIN_CHANGED')
                self.extra['job_delta']=job_delta(self.snapshots['before-reads'],self.snapshots['after-reads'],{k:v for k,v in self.approved.items() if k not in prior_approved})
            else:need(dict(before,match_id_versions=ids)==self.snapshot,'PASSIVE_READ_CHANGED_STATE')
            secrets=[self.token]+[self.cfg[k] for k in ('root_password','db_password','core_db_password','admin_password') if isinstance(self.cfg.get(k),str)]
            need(not any(value and value.encode() in raw for value in secrets for raw in self.responses),'PRIVATE_VALUE_IN_RESPONSE')
            self.check('phase_preservation_authenticated_joomla_and_known_secret_scan',phase=args.phase,provider_calls=0,service_actions=0)
            self.save(True)
    return Acceptance

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings',required=True);parser.add_argument('--bindings-sha256',required=True)
    parser.add_argument('--phase',choices=tuple(PHASES),required=True)
    parser.add_argument('--permission-receipt');parser.add_argument('--permission-sha256')
    args=parser.parse_args();test=None
    try:
        b,profile=validate_bindings(args.bindings,args.bindings_sha256);m=support_module(b,profile,args)
        mode,previous=PHASES[args.phase];base=Path(b['operation_root'])/'acceptance';prior=str(base/previous/'verification.json') if previous else None
        original=argparse.Namespace(profile=b['profile']['path'],setup=b['setup']['path'],setup_sha256=b['setup']['sha256'],expected_source=b['source_commit'],expected_version=b['version'],fresh_installation_id=b['installation_id'],output=str(base/args.phase),fresh=mode=='fresh',workflow=mode=='workflow',readback=prior if mode=='readback' else None,uninstalled=prior if mode=='uninstalled' else None,previous=prior if mode=='workflow' else None)
        test=make_acceptance(m,b,profile,args)(original);test.run();print(json.dumps({'passed':True,'phase':args.phase,'checks':len(test.checks),'report':str(test.output/'verification.json')}));return 0
    except Exception as error:
        code=str(error) if re.fullmatch('[A-Z0-9_]+',str(error)) else 'SANITIZED_SERVICE_ACCEPTANCE_FAILED'
        if test:
            test.checks.append({'name':test.stage,'status':'FAIL','code':code,'exception_type':type(error).__name__,'helper_line':traceback.extract_tb(error.__traceback__)[-1].lineno});test.save()
        print(json.dumps({'passed':False,'code':code,'exception_type':type(error).__name__}));return 1
if __name__=='__main__':raise SystemExit(main())
