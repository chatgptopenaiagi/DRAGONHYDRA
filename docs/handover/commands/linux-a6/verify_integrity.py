"""Independent file-only A6 preparation archive/wheel/input integrity receipt."""
from datetime import datetime,timezone
import hashlib,json,tarfile,zipfile
from pathlib import Path,PurePosixPath
WORK=Path(__file__).resolve().parent
ROOT=WORK.parents[2]
WINDOWS=ROOT/'build/connections/payload-20261031-a6'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
report=load(WORK/'build-report.json');manifest=load(WORK/'SOURCE-MANIFEST.json');windows=load(WINDOWS/'SOURCE-MANIFEST.json')
assert report['passed'] and report['status']=='linux_core_verified_server_requires_dependencies'
assert manifest['source_content_sha256']==report['source_content_sha256']=='3319aed91dd0bb8d74062ed2335f5817422615e30e51d11c3fc970f477de5804'
assert hashlib.sha256(canonical(manifest['files'])).hexdigest()==manifest['source_content_sha256']
assert windows['content_sha256']=='886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4'
assert len(manifest['files'])==71
for item in manifest['files']:
    for base in (WORK/'source',ROOT):
        p=base/item['path'];assert p.resolve().is_relative_to(base) and p.is_file() and not p.is_symlink()
        assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],item['path']
assert sha(ROOT/'scripts/build_linux_bundle.py')=='1eb97a451d42feccddc709042b7b86e325d2cad83d28c26f3396c8ac36ddfd9e'
inputs={x['path']:x for x in manifest['files']};win={x['path']:x for x in windows['files']}
common=inputs.keys()&win.keys();assert len(common)==62 and all(inputs[k]['sha256']==win[k]['sha256'] for k in common)
products={k:x for k,x in inputs.items() if k.startswith('src/dragonhydra/')};assert len(products)==61
wheel=next((WORK/'wheel').glob('*.whl'));assert len(list((WORK/'wheel').glob('*.whl')))==1
with zipfile.ZipFile(wheel) as z:
    names=z.namelist();assert len(names)==75 and len(names)==len(set(names))
    assert z.testzip() is None
    for name in names:
        rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
    for name,item in products.items():
        member=name.removeprefix('src/');assert hashlib.sha256(z.read(member)).hexdigest()==item['sha256']
        assert win[name]['sha256']==item['sha256']
    identity=json.loads(z.read('dragonhydra/build_info.json'))
    assert identity['source_sha'] is None and identity['source_content_sha256']==manifest['source_content_sha256']
    metadata=z.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode().replace('\r\n','\n')
    assert (WORK/'source/README.md').read_text().strip() in metadata
archive=ROOT/report['artifact']['path'];assert sha(archive)==report['artifact']['sha256']
assert archive.stat().st_size==report['artifact']['bytes']==303125
bundle=WORK/archive.name.removesuffix('.tar.gz');bundle_manifest=load(bundle/'MANIFEST.json')
assert len(bundle_manifest['files'])==8
assert (bundle/'SOURCE-MANIFEST.json').read_bytes()==(WORK/'SOURCE-MANIFEST.json').read_bytes()
assert (bundle/wheel.name).read_bytes()==wheel.read_bytes()
for item in bundle_manifest['files']:
    assert Path(item['path']).name==item['path']
    p=bundle/item['path'];assert p.is_file() and p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
with tarfile.open(archive,'r:gz') as t:
    members=t.getmembers();assert len(members)==9 and all(m.isfile() for m in members)
    assert len({m.name for m in members})==9
    for m in members:
        rel=PurePosixPath(m.name).relative_to(bundle.name);assert len(rel.parts)==1 and '..' not in rel.parts
        assert m.uid==m.gid==0 and not m.uname and not m.gname
        assert t.extractfile(m).read()==(bundle/str(rel)).read_bytes()
        assert m.mode==(0o755 if str(rel).endswith('.sh') else 0o644)
linux=report['linux'];assert linux['passed'] and linux['exit_code']==0 and linux['cli_score_cases']==4
assert linux['python_executable']=='/usr/bin/python3' and linux['python'].startswith('3.14.4 ')
missing=sorted(name for name,status in linux['preflight']['runtime']['dependencies'].items() if not status['available'])
assert missing==['fastapi','openpyxl','tzdata','uvicorn'] and linux['preflight_exit_code']==2
assert not linux['preflight']['runtime']['ready'] and not linux['server_runtime_verified'] and not linux['service_activated']
parser=load(WORK/'RETAINED-PARSER-VERIFICATION.json');contract=load(WORK/'PACKAGE3-CONTRACT-VERIFICATION.json')
for value in (parser,contract):
    assert value['passed'] and value['exit_code']==0 and value['source_content_sha256']==manifest['source_content_sha256']
    guard=value['guards'];assert guard['forbidden_operation_attempts']==0 and guard['sqlite3_definitions_imported']
    assert not guard['settings_definitions_imported'] and not guard['vault_definitions_imported']
    assert not any(guard['optional_server_modules_imported'].values())
    assert all(guard[k] is False for k in ('database_connected','grounding_run','API_started','worker_started','model_inference','services_changed'))
assert parser['event_rows']==4407 and parser['squad_entries']=={'771':24,'779':26} and parser['event_types']==29 and parser['count_groups']==181
assert parser['projection_sha256']=='6a36c2bdb29ab890fae4e0e3b13764bdef9e60d36c8682029e72740f1ab59603'
assert [x['offset'] for x in parser['pages']]==[0,2200,4400] and [x['rows'] for x in parser['pages']]==[200,200,7]
assert parser['input_files_unchanged'] and contract['input_file_unchanged']
assert contract['request_body_canonical_sha256']=='014602fe24118d588f5826607977e29110e493f713ef6d08e401a23de30510e5'
assert contract['prompt_utf8_sha256']=='7e83bfec751b59ab0a133fffcf154fe135d034016e7c624ec84ca114b882fb8a'
assert contract['synthetic_output_canonical_sha256']=='04d514665b6312ec94d478aafaeda05f5643d77eb8a6b4099b09311a7425f065'
assert contract['fact_id']=='F3' and contract['citations']==3 and len(contract['input_manifest'])==4
historical={
 'build/linux/prep-20261031-r2/dragonhydra-linux-dev-9f3d6e5ab108.tar.gz':'bda24964246f0cbc59ca096cd08558fcee77597d93980931dc8ee76c6f00fc7d',
 'build/linux/prep-20261031-a4/dragonhydra-linux-dev-09d0d818a5a3.tar.gz':'90d2a92de39ebc82c18f59e12b80dbf477cd217c5348917dd314bfb4a2d8f812',
 'build/linux/prep-20261031-a5/dragonhydra-linux-dev-ac7e694e9e38.tar.gz':'be226f95e1e7c689e8c6fd60d646c77273bfeedd43550104215773d49536e115',
 'build/linux/prep-20261031-a5-r2/dragonhydra-linux-dev-09822a188bd1.tar.gz':'dcf3c31f7fcfb11fc3170ddbdb3566eaf917e586a437de3dc93ec9d441de2562'}
# Resolve the earlier A4 filename through its own saved report, never a rescan.
old_a4=load(ROOT/'build/linux/prep-20261031-a4/build-report.json')['artifact']
historical.pop('build/linux/prep-20261031-a4/dragonhydra-linux-dev-09d0d818a5a3.tar.gz')
historical[old_a4['path'].replace('\\','/')]=old_a4['sha256']
for name,pin in historical.items():assert sha(ROOT/name)==pin
result={'schema_version':1,'passed':True,'verified_at':datetime.now(timezone.utc).isoformat(),
 'scope':'Linux A6 preparation plus actual Ubuntu CLI, retained native parser and pure package/3 contract parity; no database grounding, API/server/model/backend proof.',
 'source_content_sha256':manifest['source_content_sha256'],'windows_a6_source_content_sha256':windows['content_sha256'],
 'snapshot_files_verified':71,'common_windows_manifest_files_identical':62,'wheel_package_files_verified':61,'wheel_members':75,
 'archive_files_verified':9,'bundle_manifest_files_verified':8,'artifact':report['artifact'],
 'wheel':{'filename':wheel.name,'bytes':wheel.stat().st_size,'sha256':sha(wheel)},
 'builder_unchanged_sha256':sha(ROOT/'scripts/build_linux_bundle.py'),'linux_python':linux['python'],'linux_cli_cases':4,
 'dependency_preflight_exit_code':2,'missing_stock_interpreter_server_dependencies':missing,
 'retained_parser':{'passed':True,'event_rows':4407,'squads':{'France':24,'Argentina':26},'types':29,'count_groups':181,'projection_sha256':parser['projection_sha256'],'pages':parser['pages']},
 'package3_contract':{'passed':True,'package_bytes':3167,'package_sha256':contract['package_sha256'],'request_sha256':contract['request_body_canonical_sha256'],'prompt_sha256':contract['prompt_utf8_sha256'],'synthetic_f3_output_sha256':contract['synthetic_output_canonical_sha256'],'citations':3,'input_ids':4,'selection_is_synthetic':True},
 'sqlite_definitions_imported':True,'database_operations':0,'grounding_verified':False,'API_started':False,'worker_started':False,
 'model_inference':False,'service_activation':False,'dependency_installs':False,'downloads':False,'VPS_deployed':False,
 'source_database_read_or_backup':False,'existing_R8_api_model_profile_touched':False,'old_windows_full_scan_repeated':False,
 'historical_linux_archives_preserved':historical,
 'input_and_evidence_hashes':{name:sha(WORK/name) for name in ('SOURCE-MANIFEST.json','build-report.json','RETAINED-PARSER-VERIFICATION.json','PACKAGE3-CONTRACT-VERIFICATION.json','wheel_guard.py','retained-parser-smoke.py','retained-package-contract-smoke.py')},
 'limits':['Missing dependencies describe the stock /usr/bin/python3 preflight, not the separate R8 owner vendored runtime.',
  'The real prior Qwen/API-worker selection was source-only F1/E1; F3 here is a synthetic local contract call without inference.',
  'No WSL service/process/configuration health or mutation probe was performed. Existing R8 ownership remains separate.']}
path=WORK/'INTEGRITY-VERIFICATION.json';assert not path.exists();path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'snapshot_files':71,'wheel_product_files':61,'windows_common_files':62,'wheel_members':75,
 'artifact':report['artifact'],'wheel':result['wheel'],'stock_preflight_exit_code':2,'missing_dependencies':missing,
 'parser4407_passed':True,'package3_contract_parity_passed':True,'API_model_DB_started':False,'integrity_receipt_sha256':sha(path)},indent=2))
