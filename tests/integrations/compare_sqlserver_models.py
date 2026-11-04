"""Offline same-input numerical replay of frozen795, feature and SQL publication.

Reads only named archived JSON and an immutable SQLite backup. The snapshot is
projected with the frozen existing reader in a memory-only copy. Two independent
Python workers call the existing pure models with identical rows/raw bytes,
cutoff/configuration and ORIGINAL generation clock. No SQLServer connection,
HTTP, provider, profile, job submission or forecast persistence is performed.
This retrospective value comparison establishes neither predictive skill nor a
new forecast's historical availability.
"""
from __future__ import annotations
import argparse,base64,copy,hashlib,io,json,os,re,sqlite3,stat,subprocess,sys
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path,PurePosixPath
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'runtime/sqlserver-evidence'
BASELINE='795f962be36d30f8c30bcb1a2c3dc264b9b397e3'
GIT=r'C:\Program Files\Git\cmd\git.exe'
NAMES={'frequency','poisson_goals','elo','recency','ensemble'}
OUTCOMES=('home','draw','away')


def require(condition,code):
    if not condition:raise ValueError(code)


def ordinary(path,*,inside=None):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        if item.exists():require(not item.is_symlink() and not getattr(item.lstat(),'st_file_attributes',0)&0x400,'REPARSE_PATH_REFUSED')
    if inside:require(path.is_relative_to(Path(inside).absolute()) and path!=Path(inside).absolute(),'OUTPUT_OUTSIDE_OWNED_EVIDENCE')
    return path


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(path):
    path=ordinary(path);require(path.is_file() and path.stat().st_size<=32*1024*1024,'INPUT_MISSING_OR_OVERSIZED')
    return json.loads(path.read_text(encoding='utf-8-sig'),parse_constant=lambda v:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
def write_new(path,value):
    with ordinary(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
def utc(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'));require(parsed.utcoffset() is not None,'NAIVE_CLOCK_REFUSED')
    return parsed.astimezone(timezone.utc)


def number(value):
    require(type(value) in (str,int,float),'INVALID_NUMERIC_VALUE')
    result=Decimal(str(value));require(result.is_finite(),'NONFINITE_MODEL_VALUE');return result


def numeric_tree(value,path=''):
    result={}
    if type(value) in (int,float):result[path]=str(number(value))
    elif isinstance(value,dict):
        for key,item in value.items():result.update(numeric_tree(item,path+'/'+str(key)))
    elif isinstance(value,list):
        for index,item in enumerate(value):result.update(numeric_tree(item,path+'/'+str(index)))
    return result


def result_projection(results):
    require(set(results)==NAMES,'EXACT_FIVE_MODELS_REQUIRED')
    vectors={};numeric={}
    for name,result in results.items():
        if name!='ensemble':require(result.get('available') is True,'MODEL_UNAVAILABLE:'+name)
        values=result['probabilities'];require(set(values)==set(OUTCOMES),'INCOMPLETE_MODEL_VECTOR')
        vectors[name]={k:str(number(values[k]['value'] if isinstance(values[k],dict) else values[k])) for k in OUTCOMES}
        require(abs(sum(Decimal(v) for v in vectors[name].values())-1)<=Decimal('1e-12'),'MODEL_VECTOR_NOT_NORMALIZED')
        numeric[name]=numeric_tree(result)
    return dict(vectors=vectors,numeric=numeric)


def loaded_sources(module_root):
    rows=[]
    for name,module in sorted(sys.modules.items()):
        if name=='dragonhydra' or name.startswith('dragonhydra.'):
            path=getattr(module,'__file__',None)
            if path:
                path=ordinary(path);require(path.is_relative_to(module_root/'src'),'MIXED_MODULE_SOURCE')
                rows.append(dict(module=name,path=path.relative_to(module_root).as_posix(),sha256=digest(path)))
    return rows


def worker(mode,module_root,request_path):
    module_root=ordinary(module_root);request=read(request_path)
    sys.path.insert(0,str(module_root/'src'))
    if mode=='extract':
        from dragonhydra import public_results
        snapshot=ordinary(request['snapshot']);require(re.fullmatch(r'\d\d-.+\.sqlite3',snapshot.name),'NAMED_COHERENT_SNAPSHOT_REQUIRED')
        before=digest(snapshot)
        source=sqlite3.connect(snapshot.as_uri()+'?mode=ro&immutable=1',uri=True)
        memory=sqlite3.connect(':memory:')
        try:
            source.execute('PRAGMA query_only=ON');require(source.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SNAPSHOT_INTEGRITY_FAILED')
            source.backup(memory)
            tables={r[0] for r in memory.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'connector_records' in tables:require(memory.execute('SELECT COUNT(*) FROM connector_records').fetchone()[0]==0,'CONNECTOR_ROWS_REQUIRE_EXPLICIT_PROJECTION')
            rows=public_results.latest(memory,request['cutoff'])
            required={r['source_hash'] for r in rows};raw={}
            for sha in required:
                found=memory.execute('SELECT bytes FROM raw_sources WHERE source_hash=?',(sha,)).fetchone();require(found is not None,'RAW_SOURCE_MISSING')
                blob=bytes(found[0]);require(hashlib.sha256(blob).hexdigest()==sha,'RAW_SOURCE_HASH_MISMATCH');raw[sha]=base64.b64encode(blob).decode()
        finally:source.close();memory.close()
        require(digest(snapshot)==before,'SNAPSHOT_CHANGED')
        return dict(rows=rows,raw_sources=raw,snapshot_sha256=before,projection='Existing frozen public_results.latest on an in-memory copy; disk coherent backup mode=ro&immutable=1',loaded_sources=loaded_sources(module_root))
    from dragonhydra.cognition import models
    from dragonhydra import research
    evidence=read(request['inputs']);rows=evidence['rows'];target=request['target'];clock=utc(request['generated_at'])
    class OriginalClock(datetime):
        @classmethod
        def now(cls,tz=None):return cls.fromtimestamp(clock.timestamp(),tz=tz or timezone.utc)
    models.datetime=research.datetime=OriginalClock
    raw={sha:base64.b64decode(blob,validate=True) for sha,blob in evidence['raw_sources'].items()}
    require(all(hashlib.sha256(blob).hexdigest()==sha for sha,blob in raw.items()),'RAW_SOURCE_HASH_MISMATCH')
    result=models.forecast(rows,target,request['cutoff'],lambda sha:raw[sha],config=request['configuration'],
                           performance_records=request.get('performance_records',[]),
                           performance_resolver=lambda eid:request.get('performance_evidence',{})[eid])
    results={**result['models'],'ensemble':result['ensemble']}
    require(result['ensemble'] is not None,'ENSEMBLE_UNAVAILABLE')
    return dict(**result_projection(results),training_manifest=result['training_manifest'],training_count=result['training_count'],
                target=result['target'],configuration=result['configuration']['values'],weight_mode=result['ensemble']['weight_mode'],
                model_version=result['model_version'],replay_clock=clock.isoformat(),loaded_sources=loaded_sources(module_root))


def child(mode,module_root,request_path,output):
    env=dict(os.environ);env['PYTHONPATH']=str(module_root/'src');env['PYTHONNOUSERSITE']='1';env['PYTHONPYCACHEPREFIX']=str(output/('unused-pycache-'+('baseline' if module_root!=ROOT else 'feature')))
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--_worker',mode,'--_module-root',str(module_root),'--_request',str(request_path)],
                          env=env,cwd=output,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',timeout=90)
    (output/(mode+'-'+('baseline' if module_root!=ROOT else 'feature')+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
    require(result.returncode==0,'OFFLINE_WORKER_FAILED:'+mode)
    return json.loads(result.stdout)


def compare(left,right,label):
    require(set(left['vectors'])==set(right['vectors'])==NAMES,'MODEL_SET_CHANGED:'+label)
    values=[]
    for name in sorted(NAMES):
        for outcome in OUTCOMES:
            a,b=number(left['vectors'][name][outcome]),number(right['vectors'][name][outcome])
            require(a==b,'NUMERICAL_VECTOR_DIFFERENCE:'+label+':'+name+':'+outcome)
            values.append(dict(model=name,outcome=outcome,left=str(a),right=str(b),absolute_delta=str(abs(a-b))))
        require(set(left['numeric'][name])==set(right['numeric'][name]),'NUMERIC_FIELD_SET_CHANGED:'+label+':'+name)
        require(all(number(v)==number(right['numeric'][name][key]) for key,v in left['numeric'][name].items()),'NUMERIC_RESULT_DIFFERENCE:'+label+':'+name)
    return dict(label=label,probability_values=len(values),numeric_result_values=sum(len(v) for v in left['numeric'].values()),maximum_absolute_delta='0',values=values)


def run(args):
    output=ordinary(args.output,inside=EVIDENCE);require(not output.exists(),'FRESH_NUMERICAL_OUTPUT_REQUIRED')
    archive_path,forecast_path,snapshot=(ordinary(v,inside=EVIDENCE) for v in (args.archive,args.forecast,args.snapshot))
    wrapped=read(archive_path);bundle=wrapped['archive'];original=read(forecast_path)
    require(bundle['schema_version']=='dragonhydra.research-archive/1','ARCHIVE_SCHEMA_MISMATCH')
    require(wrapped['storage']['provider']=='sqlserver','SQL_PUBLICATION_READ_RESPONSE_REQUIRED')
    require(hashlib.sha256(canonical(bundle)).hexdigest()==wrapped['storage']['payload_sha256'],'SQL_PAYLOAD_HASH_MISMATCH')
    by_name={r['model_name']:r for r in bundle['models']};require(set(by_name)==NAMES and len(bundle['models'])==5,'EXACT_FIVE_ARCHIVED_MODELS_REQUIRED')
    require({r['record_id']:r for r in original['model_runs']}=={r['record_id']:r for r in bundle['models']},'ORIGINAL_MODEL_RECORDS_CHANGED')
    require({r['record_id']:r for r in original['predictions']}=={r['record_id']:r for r in bundle['predictions']},'ORIGINAL_PREDICTION_RECORDS_CHANGED')
    require(original['match_id']==bundle['match_id'] and original['run_id']==bundle['forecast_run_id'],'ORIGINAL_RUN_IDENTITY_MISMATCH')
    cutoff=next(iter(by_name.values()))['data_cutoff'];generated=next(iter(by_name.values()))['parameters']['workflow']['generated_at']
    config=next(iter(by_name.values()))['configuration']['values']
    require(all(utc(r['data_cutoff'])==utc(cutoff) and utc(r['parameters']['workflow']['generated_at'])==utc(generated) and r['configuration']['values']==config for r in by_name.values()),'MIXED_ARCHIVE_CONFIGURATION_OR_CLOCK')
    require(utc(cutoff)<=utc(generated),'GENERATION_BEFORE_CUTOFF')
    require(all(r['training_manifest']==bundle['input_manifest'] for r in by_name.values()),'MIXED_ARCHIVE_INPUT_MANIFEST')
    targets=[p['target_evidence'] for p in bundle['predictions']];require(len(targets)==5 and all(t==targets[0] for t in targets),'MIXED_TARGET_SNAPSHOT')
    archived_results={name:row['parameters']['result'] for name,row in by_name.items()}
    archived=result_projection(archived_results)
    model_ids={r['record_id']:r['model_name'] for r in bundle['models']}
    require(len(bundle['predictions'])==5,'EXACT_FIVE_PREDICTIONS_REQUIRED')
    for prediction in bundle['predictions']:
        name=model_ids[prediction['model_run_id']]
        require(all(number(prediction['probabilities'][k])==number(archived['vectors'][name][k]) for k in OUTCOMES),'ARCHIVE_PREDICTION_VALUE_CHANGED')
    original_results={**original['forecast']['models'],'ensemble':original['forecast']['ensemble']}
    original_projection=result_projection(original_results)
    compare(archived,original_projection,'sql_archive_vs_original_generation')
    output.mkdir(parents=True)
    baseline_root=output/'baseline-src';baseline_root.mkdir()
    archive=subprocess.check_output([GIT,'--no-optional-locks','-C',str(ROOT),'archive','--format=zip',BASELINE,'src/dragonhydra'],timeout=30)
    with ZipFile(io.BytesIO(archive)) as exported:
        for entry in exported.infolist():
            parts=PurePosixPath(entry.filename).parts
            if entry.is_dir() and parts==('src',):(baseline_root/'src').mkdir(exist_ok=True);continue
            require(parts[:2]==('src','dragonhydra') and '..' not in parts and not entry.filename.startswith('/'),'UNSAFE_GIT_ARCHIVE_PATH')
            require(stat.S_IFMT(entry.external_attr>>16)!=stat.S_IFLNK,'GIT_SYMLINK_REFUSED')
            target=baseline_root.joinpath(*parts)
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(exported.read(entry))
    feature_head=subprocess.check_output([GIT,'--no-optional-locks','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    input_hashes={str(p.relative_to(ROOT)):digest(p) for p in (archive_path,forecast_path,snapshot)}
    snapshot_family={p.name:digest(p) for p in snapshot.parent.glob(snapshot.name+'*') if p.is_file()}
    extract_request=output/'extract-request.json';write_new(extract_request,dict(snapshot=str(snapshot),cutoff=cutoff))
    evidence=child('extract',baseline_root,extract_request,output);inputs_path=output/'inputs.json';write_new(inputs_path,evidence)
    rows={r['evidence_id']:r for r in evidence['rows']};require(len(rows)==len(evidence['rows']),'DUPLICATE_INPUT_EVIDENCE_ID')
    require(all(row['evidence_id'] in rows and all(rows[row['evidence_id']].get(k)==v for k,v in row.items()) for row in bundle['input_manifest']),'INPUT_MANIFEST_SNAPSHOT_MISMATCH')
    target_snapshot=targets[0];require(target_snapshot['evidence_id'] in rows,'TARGET_ROW_MISSING');target=rows[target_snapshot['evidence_id']]
    require(all(target.get(k)==v for k,v in target_snapshot.items()),'TARGET_SNAPSHOT_MISMATCH')
    require(archived_results['ensemble']['weight_mode']!='EVALUATION_WEIGHTS','PERFORMANCE_WEIGHTED_REPLAY_NEEDS_EXPLICIT_EVIDENCE_ADAPTER')
    request_path=output/'forecast-request.json';write_new(request_path,dict(inputs=str(inputs_path),target=target,cutoff=cutoff,generated_at=generated,configuration=config))
    frozen=child('forecast',baseline_root,request_path,output);feature=child('forecast',ROOT,request_path,output)
    expected_ids=[r['evidence_id'] for r in bundle['input_manifest']]
    for report in (frozen,feature):
        require([r['evidence_id'] for r in report['training_manifest']]==expected_ids,'RECOMPUTED_TRAINING_COHORT_CHANGED')
        require(all(all(report['training_manifest'][i].get(k)==v for k,v in row.items()) for i,row in enumerate(bundle['input_manifest'])),'RECOMPUTED_TRAINING_VALUES_CHANGED')
        require(report['configuration']==config,'RECOMPUTED_CONFIGURATION_CHANGED')
        require(report['weight_mode']==archived_results['ensemble']['weight_mode'],'RECOMPUTED_WEIGHT_MODE_CHANGED')
    checks=[compare(frozen,feature,'frozen795_vs_feature'),compare(archived,frozen,'sql_archive_vs_frozen795'),compare(archived,feature,'sql_archive_vs_feature'),compare(original_projection,feature,'original_generation_vs_feature')]
    for row in feature['loaded_sources']:
        raw=subprocess.check_output([GIT,'--no-optional-locks','-C',str(ROOT),'show',feature_head+':'+row['path']],timeout=15)
        require(hashlib.sha256(raw).hexdigest()==row['sha256'],'FEATURE_LOADED_SOURCE_DIFFERS_FROM_COMMIT')
    write_new(output/'frozen-models.json',frozen);write_new(output/'feature-models.json',feature)
    require(all(digest(ROOT/p)==sha for p,sha in input_hashes.items()),'INPUT_CHANGED_DURING_COMPARISON')
    family_after={p.name:digest(p) for p in snapshot.parent.glob(snapshot.name+'*') if p.is_file()}
    require(snapshot_family==family_after,'SNAPSHOT_FAMILY_CHANGED_DURING_COMPARISON')
    receipt=dict(schema_version='dragonhydra.same-input-numerical-comparison/1',status='PASS',comparison_recorded_at=datetime.now(timezone.utc).isoformat(),baseline_source_commit=BASELINE,feature_source_commit=feature_head,
                 archive_id=bundle['archive_id'],forecast_run_id=bundle['forecast_run_id'],match_id=bundle['match_id'],data_cutoff=cutoff,original_generation_clock=generated,
                 input_hashes=input_hashes,snapshot_family_before=snapshot_family,snapshot_family_after=family_after,coherent_snapshot_sha256=evidence['snapshot_sha256'],full_as_of_rows=len(evidence['rows']),training_cohort=len(expected_ids),raw_source_documents=len(evidence['raw_sources']),
                 models=sorted(NAMES),numeric_checks=checks,original_five_model_records_preserved=True,original_five_prediction_records_preserved=True,sql_payload_hash_verified=True,
                 frozen_loaded_sources=frozen['loaded_sources'],feature_loaded_sources=feature['loaded_sources'],snapshot_changed=False,sqlserver_connections=0,live_database_access=False,
                 forecast_persistence=False,clock_scope='Explicit retrospective replay at original generation instant; no backdated operational forecast.',
                 claim='Exact same-input numerical equality for this cohort only; no statistical accuracy/calibration or new predictive-skill claim.')
    write_new(output/'verification.json',receipt)
    print(json.dumps(dict(status='PASS',feature_source_commit=feature_head,baseline_source_commit=BASELINE,models=sorted(NAMES),training_cohort=len(expected_ids),probability_values=15,maximum_absolute_delta='0',verification=str(output/'verification.json'))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path);parser.add_argument('--forecast',type=Path);parser.add_argument('--snapshot',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--_worker',choices=('extract','forecast'),help=argparse.SUPPRESS);parser.add_argument('--_module-root',type=Path,help=argparse.SUPPRESS);parser.add_argument('--_request',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args._worker:print(json.dumps(worker(args._worker,args._module_root,args._request),ensure_ascii=False,allow_nan=False));return
    require(all((args.archive,args.forecast,args.snapshot,args.output)),'EXPLICIT_OFFLINE_INPUTS_AND_FRESH_OUTPUT_REQUIRED');run(args)

if __name__=='__main__':main()