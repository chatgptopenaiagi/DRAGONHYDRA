"""Fixed b447 GET-only readback. No product-action submission branch exists."""
import argparse,ast,hashlib,http.cookiejar,importlib.util,json,re,sqlite3,sys,time
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
HERE=Path(__file__).parent
for walk in (HERE/'continuation_contract.py',*(HERE/'continuation_contract.py').parents):
    if walk.exists():
        s=walk.lstat()
        if walk.is_symlink() or getattr(s,'st_file_attributes',0)&0x400:raise RuntimeError('REPARSE_CODE_ANCESTOR_REJECTED')
spec=importlib.util.spec_from_file_location('continuation_contract',HERE/'continuation_contract.py');cc=importlib.util.module_from_spec(spec);spec.loader.exec_module(cc)
LAB=cc.ROOT.parents[1];STATE=LAB/'profiles'/cc.ID/'state';INSTALL=LAB/'profiles'/cc.ID/'application';OUT=None
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return cc.canonical(x)
def digest(p):return sha(Path(p).read_bytes())
gate=cc.need
PHASES={'reconcile':None,'backup':'reconcile'}
def validate_state_inputs():
    cc.ordinary(STATE/'kernel/core.sqlite3',STATE)
    for relative in ('workstation.json','first-run.json','site/configuration.php','client/local-session.json','kernel/product.json','web-config/httpd.conf','web-config/php.ini','web-config/my.ini'):cc.ordinary(STATE/relative,STATE)
    vault=STATE/'kernel/vault';stack=[vault] if vault.exists() else [];count=0
    while stack:
        path=stack.pop();cc.ordinary(path,STATE,False);count+=1;gate(count<=100,'VAULT_INVENTORY_BOUND')
        if path.is_dir():stack.extend(path.iterdir())
        else:gate(path.is_file(),'ORDINARY_VAULT_FILE_REQUIRED')
def live_projection():
    source=cc.ordinary(STATE/'kernel/core.sqlite3',STATE)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('pragma query_only=on');c.execute('begin');gate(c.execute('pragma integrity_check').fetchone()[0]=='ok','SQLITE_PREFLIGHT_INTEGRITY')
        schema=list(c.execute('select type,name,tbl_name,sql from sqlite_master order by type,name'));tables={};auth={}
        for name, in c.execute("select name from sqlite_master where type='table' order by name"):
            gate(bool(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name)),'SAFE_PREFLIGHT_TABLE_REQUIRED');cols=[r[1] for r in c.execute('pragma table_info("'+name+'")')];order=','.join('"'+x.replace('"','""')+'"' for x in cols);h=hashlib.sha256();count=0
            for row in c.execute('select * from "'+name+'" order by '+order):count+=1;h.update(canonical([atom(x) for x in row])+b'\n')
            (auth if name in ('product_sessions','product_bridge_nonces') else tables)[name]={'rows':count,'sha256':h.hexdigest()}
        jobs=c.execute('select count(*) from product_jobs').fetchone()[0];active=c.execute("select count(*) from product_jobs where status in ('queued','running')").fetchone()[0];c.rollback()
    gate(active==0,'ACTIVE_JOB_RECONCILIATION_REQUIRED');return {'schema_sha256':sha(canonical(schema)),'protected_tables':tables,'auth_bookkeeping':auth,'job_count':jobs,'integrity_check':'ok'}
def imports():
    audited=cc.ordinary(LAB/'verify_disposable_workstation_dev5.py',LAB);gate(digest(audited)=='47d5ffc472bbb0675ab8942c77fccb14e9a780e8f40acff2e397fe5e1c197f0b','AUDITED_DEFINITIONS_CHANGED')
    names={'GateError','gate','NoRedirect','guard_service_identity','guard_identity_payload'};tree=ast.parse(audited.read_text(encoding='utf-8-sig'));nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names];gate({n.name for n in nodes}==names,'EXACT_READ_DEFINITIONS_REQUIRED');exec(compile(ast.Module(body=nodes,type_ignores=[]),str(audited)+'#readonly-definitions','exec'),globals())
    snapshot=cc.ordinary(cc.ROOT/'installed-joomla-history-r1/read_history.py',cc.ROOT);gate(digest(snapshot)=='cbe3b9dcbeff1b871d46faa73123c019123db5f21a877d055596ef279a768991','AUDITED_SNAPSHOT_DEFINITIONS_CHANGED')
    names={'atom','db_snapshot','configuration'};tree=ast.parse(snapshot.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names];gate({n.name for n in nodes}==names,'EXACT_SNAPSHOT_DEFINITIONS_REQUIRED');exec(compile(ast.Module(body=nodes,type_ignores=[]),str(snapshot)+'#snapshot-only','exec'),globals())
def run(a):
    global OUT
    gate(a.phase in PHASES,'PHASE_NOT_IMPLEMENTED')
    receipt,baseline=cc.validate({'path':a.receipt,'sha256':a.receipt_sha256},{'path':a.approval,'sha256':a.approval_sha256})
    OUT=cc.ordinary(a.output,cc.OP,False);gate(OUT==cc.OP/'acceptance'/a.phase and not OUT.exists(),'EXACT_FRESH_ACCEPTANCE_OUTPUT_REQUIRED')
    prior=PHASES[a.phase]
    if prior:
        gate(a.previous is not None and Path(a.previous)==cc.OP/'acceptance'/prior/'verification.json','EXACT_NEW_PREDECESSOR_REQUIRED');previous=json.loads(cc.ordinary(a.previous,cc.OP).read_text())
        gate(previous.get('schema_version')=='dev5.forecast-continuation-readback/1' and previous.get('passed') is True and previous.get('phase')==prior and previous.get('operation_id')==cc.OPID and previous.get('reconciliation_sha256')==a.receipt_sha256,'SUCCESSFUL_NEW_PREDECESSOR_REQUIRED')
    else:gate(a.previous is None,'RECONCILE_HAS_NO_OLD_PASS_PREDECESSOR')
    if not a.validate_only:
        phase_name={'reconcile':'ReconcileForecast','backup':'Backup'}[a.phase]
        context=json.loads(cc.ordinary(cc.OP/('phase-'+phase_name+'.json'),cc.OP).read_text())
        gate(context.get('schema_version')=='dev5.forecast-continuation-phase/1' and context.get('stage')=='validated_before_action' and context.get('operation_id')==cc.OPID and context.get('phase')==phase_name and context.get('operation_acl_verified') is True and context.get('reconciliation',{}).get('sha256')==a.receipt_sha256 and context.get('approval',{}).get('sha256')==a.approval_sha256,'REVIEWED_PRIVATE_CONTROLLER_CONTEXT_REQUIRED')
        cc.ordinary(cc.OP/(phase_name+'.started.lock'),cc.OP)
        OUT.mkdir(parents=True);(OUT/'private').mkdir();cc.ordinary(OUT/'private',cc.OP,False)
    report={'schema_version':'dev5.forecast-continuation-readback/1','operation_id':cc.OPID,'phase':a.phase,'passed':False,'expected_source':cc.SOURCE,'source_commit':cc.SOURCE,'version':cc.VERSION,'installation_id':cc.ID,'setup_sha256':cc.SETUP,'reconciliation_sha256':a.receipt_sha256,'approval_sha256':a.approval_sha256,'helper_sha256':digest(__file__),'requests':[],'checks':[],'product_action_posts':0,'original_forecast_status':'FAIL'}
    try:
        imports();profile=json.loads(cc.ordinary(LAB/'profiles'/cc.ID/'installation-profile.json',LAB).read_text(encoding='utf-8-sig'));cfg=json.loads(cc.ordinary(STATE/'workstation.json',LAB).read_text(encoding='utf-8-sig'))
        gate(all(profile.get(k)==v and cfg.get(k)==v for k,v in {'installation_id':cc.ID,'source_commit':cc.SOURCE,'version':cc.VERSION}.items()) and profile['ports']=={'api':18860,'web':18861,'database':18862} and [cfg['api_port'],cfg['web_port'],cfg['database_port']]==[18860,18861,18862],'EXACT_INSTALLED_CONFIG_REQUIRED')
        validate_state_inputs();before_config=configuration()
        if a.validate_only:before=live_projection()
        else:
            cc.ordinary(OUT/'private/before-reads.sqlite3',cc.OP,False);gate(not(OUT/'private/before-reads.sqlite3').exists(),'FRESH_SNAPSHOT_REQUIRED');before=db_snapshot('before-reads')
        approved=baseline['database_after']
        gate(before['schema_sha256']==approved['schema_sha256'] and before['protected_tables']==approved['protected_tables'] and before['job_count']==approved['job_count'] and before_config==baseline['configuration_fingerprints'],'APPROVED_COMPLETE_BASELINE_DRIFT')
        offline=a.phase in ('uninstalled','final-uninstalled')
        if offline:gate(not INSTALL.exists(),'ENTIRE_OWN_RUNTIME_MUST_BE_REMOVED')
        else:
            binding=json.loads((cc.OLD/'BINDINGS.json').read_text());gate(digest(INSTALL/'WORKSTATION-BUILD.json')==binding['workstation_build_sha256'] and digest(INSTALL/'PAYLOAD-MANIFEST.json')==binding['payload_manifest_sha256'],'INSTALLED_MANIFEST_CHANGED');build=json.loads((INSTALL/'WORKSTATION-BUILD.json').read_text());gate(len(build['application_components'])==5 and build['source_sha']==cc.SOURCE and build['version']==cc.VERSION,'INSTALLED_COMPONENT_SET_REQUIRED')
            for row in build['application_components']:
                file=cc.ordinary(INSTALL/row['path'],INSTALL);gate(file.stat().st_size==row['bytes'] and digest(file)==row['sha256'] and row['source_commit']==cc.SOURCE,'INSTALLED_COMPONENT_CHANGED')
            token=json.loads(cc.ordinary(STATE/'client/local-session.json',STATE).read_text(encoding='utf-8-sig'))['token'];opener=build_opener(ProxyHandler({}),NoRedirect());base='http://127.0.0.1:18860/dragon/api/v1'
            allowed={'/health/ready','/system','/modules?scope=all','/jobs/'+cc.FORECAST,'/jobs/'+cc.EVALUATION,'/matches/'+cc.TARGET+'/cognition-history'}
            def get(path):
                gate(path in allowed,'GET_OUTSIDE_FIXED_SCOPE')
                with opener.open(Request(base+path,headers={'Authorization':'Bearer '+token},method='GET'),timeout=20) as r:gate(r.status==200,'READBACK_HTTP_STATUS');raw=r.read(8*1024*1024+1)
                gate(len(raw)<=8*1024*1024 and token.encode() not in raw,'RESPONSE_BOUND_OR_SECRET_FAILURE');report['requests'].append({'method':'GET','path':path});return json.loads(raw)
            health=get('/health/ready');identity=get('/system')['installation'];gate(health.get('source_sha')==cc.SOURCE and health.get('version')==cc.VERSION and identity.get('installation_id')==cc.ID and identity.get('source_commit')==cc.SOURCE,'LIVE_IDENTITY_MISMATCH')
            deadline=time.monotonic()+60
            while True:
                modules=get('/modules?scope=all');item=next((x for x in modules['items'] if x.get('id')=='runtime_supervisor'),{})
                try:service=guard_service_identity(item,profile);break
                except GateError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(1)
            history=get('/matches/'+cc.TARGET+'/cognition-history');gate(history['installation']['installation_id']==cc.ID and sha(canonical(history['records']))==cc.HISTORY and {k:len(v) for k,v in history['records'].items()}=={'models':5,'predictions':5,'outcomes':0,'evaluations':0},'ORIGINAL_HISTORY_CHANGED')
            jobs={j:get('/jobs/'+j) for j in (cc.FORECAST,cc.EVALUATION)};gate(all(j['status']=='succeeded' and j['payload']['match_id']==cc.TARGET for j in jobs.values()) and jobs[cc.FORECAST]['kind']=='forecast' and jobs[cc.EVALUATION]['kind']=='evaluation' and jobs[cc.EVALUATION]['result']['status']=='pending','ORIGINAL_TWO_JOBS_OR_PENDING_RESULT_CHANGED')
            report['workflow']={'forecast_job_id':cc.FORECAST,'evaluation_job_id':cc.EVALUATION,'history_records_sha256':cc.HISTORY,'record_ids':{k:[r['record_id'] for r in v] for k,v in history['records'].items()},'counts':history['counts'],'new_operations_submitted':0};report['service_identity']=service
        validate_state_inputs()
        if a.validate_only:after=live_projection()
        else:
            cc.ordinary(OUT/'private/after-reads.sqlite3',cc.OP,False);gate(not(OUT/'private/after-reads.sqlite3').exists(),'FRESH_SNAPSHOT_REQUIRED');after=db_snapshot('after-reads')
        config_after=configuration();gate(before['schema_sha256']==after['schema_sha256'] and before['protected_tables']==after['protected_tables'] and before_config==config_after,'READS_MUTATED_PROTECTED_STATE')
        report.update(snapshot=after,configuration_fingerprints=config_after,offline=offline,passed=True,validate_only=a.validate_only)
        if not a.validate_only:report['sqlite_consistent_snapshot']={'path':after['private_snapshot'],'sha256':after['snapshot_sha256'],'integrity_check':'ok','consistent_backup':True}
        report['checks'].append({'name':'new_approved_baseline_original_jobs_and_full_protected_state','status':'PASS'})
        if a.previous:report['predecessor_receipt']={'path':a.previous,'sha256':digest(a.previous),'phase':prior}
    except Exception as e:report['error_type']=type(e).__name__;report['error_code']=str(e) if re.fullmatch('[A-Z0-9_]+',str(e)) else 'SANITIZED_READBACK_FAILURE'
    report['observed_at']=datetime.now(timezone.utc).isoformat()
    if a.validate_only:report['output_created']=False;print(json.dumps(report));return 0 if report['passed'] else 2
    path=OUT/'verification.json';tmp=OUT/'verification.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(path);print(json.dumps({'passed':report['passed'],'receipt':str(path),'sha256':digest(path)}));return 0 if report['passed'] else 2
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--receipt',required=True);p.add_argument('--receipt-sha256',required=True);p.add_argument('--approval',required=True);p.add_argument('--approval-sha256',required=True);p.add_argument('--phase',choices=PHASES,required=True);p.add_argument('--output',required=True);p.add_argument('--previous');p.add_argument('--validate-only',action='store_true');a=p.parse_args()
    try:raise SystemExit(run(a))
    except cc.Refused as e:print(json.dumps({'passed':False,'error_code':str(e)}));raise SystemExit(2)
