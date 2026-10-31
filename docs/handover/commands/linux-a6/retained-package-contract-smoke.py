"""Linux real-wheel pure package/3 contract parity, SYNTHETIC F3 selection only."""
import hashlib,json
from pathlib import Path
import sys
ROOT=Path('/mnt/c/xampp/DRAGONHYDRA')
WORK=ROOT/'build/linux/prep-20261031-a6'
SITE=WORK/'linux-smoke/site-packages'
sys.path.insert(0,str(WORK))
from wheel_guard import guarded_wheel

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
source=json.loads((WORK/'SOURCE-MANIFEST.json').read_text())['source_content_sha256']
package_path=ROOT/'build/connections/sports-package-3-20261031/qwen-api-r1/sports-package.json'
before=sha(package_path)
assert before=='e0f2f312cd1fc55198be776f1bd6466a10ec3a3f52b5810e2b36a22d4c424b92'
with guarded_wheel(WORK,SITE) as guard:
    from dragonhydra import local_ai,local_ai_context
    from dragonhydra.build_meta import info
    assert Path(local_ai_context.__file__).resolve().is_relative_to(SITE)
    assert info()['source_content_sha256']==source and info()['source_sha'] is None
    raw=package_path.read_bytes();package=json.loads(raw)
    assert len(raw)==3167 and package['package_sha256']=='60802e4502eac8a38e638d6711a302ac716d2711131c101ff221de87444a0aa6'
    assert local_ai.validate_package(package)==package
    request=local_ai.request_body(package)
    accepted=local_ai.validate_output(package,'{"fact_id":"F3"}')
    canonical=local_ai.canonical
    assert hashlib.sha256(canonical({k:v for k,v in package.items() if k!='package_sha256'})).hexdigest()==package['package_sha256']
    request_hash=hashlib.sha256(canonical(request)).hexdigest();prompt_hash=hashlib.sha256(request['prompt'].encode()).hexdigest();output_hash=hashlib.sha256(canonical(accepted)).hexdigest()
    assert len(canonical(request))==1162 and request_hash=='014602fe24118d588f5826607977e29110e493f713ef6d08e401a23de30510e5'
    assert len(request['prompt'].encode())==806 and prompt_hash=='7e83bfec751b59ab0a133fffcf154fe135d034016e7c624ec84ca114b882fb8a'
    assert len(canonical(accepted))==3079 and output_hash=='04d514665b6312ec94d478aafaeda05f5643d77eb8a6b4099b09311a7425f065'
    evidence,context=package['evidence']['E1'],package['evidence']['C1']
    assert accepted['observation']=='The retained StatsBomb event document contains 4407 event rows.'
    assert accepted['fact_id']=='F3' and accepted['evidence_aliases']==['E1','C1'] and len(accepted['evidence'])==3
    assert accepted['input_manifest']==[evidence['id'],context['id'],context['documents']['events']['id'],context['documents']['lineups']['id']]
    assert accepted['evidence'][0]=={'id':evidence['id'],'url':'/dragon/api/v1/evidence/'+evidence['id'],'label':'Retained source record'}
    for role,item in zip(('events','lineups'),accepted['evidence'][1:]):
        assert all(item[k]==v for k,v in context['documents'][role].items())
        assert item['role']==role and item['context_record_id']==context['id'] and item['context_record_sha256']==context['record_sha256']
        assert item['parent_observation_id']==evidence['id'] and all(item[k]==context[k] for k in ('received_at','persisted_at','usable_at'))
        assert item['url']=='/dragon/api/v1/connections/statsbomb/acquisitions/'+context['documents'][role]['id']
    assert sha(package_path)==before
    print(json.dumps({'passed':True,'scope':'Linux wheel pure contract parity only; SYNTHETIC F3 selection, no grounding/API/model inference.',
        'python':sys.version,'python_executable':sys.executable,'wheel_module':str(Path(local_ai_context.__file__).relative_to(ROOT)),
        'source_content_sha256':source,'package_bytes':3167,'package_sha256':package['package_sha256'],'package_file_sha256':before,
        'request_body_canonical_sha256':request_hash,'request_body_canonical_bytes':1162,'prompt_utf8_sha256':prompt_hash,'prompt_utf8_bytes':806,
        'synthetic_output_canonical_sha256':output_hash,'synthetic_output_canonical_bytes':3079,'fact_id':'F3','citations':3,'input_manifest':accepted['input_manifest'],
        'input_file_unchanged':True,'guards':guard.report(),'server_runtime_verified':False,'model_inference':False,'grounding_verified':False},ensure_ascii=False))
