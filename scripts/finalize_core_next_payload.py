"""Finalize only a prepared lab payload; no installer, service or guest action."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os
from verify_core_next_payload import verify

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    temporary=path.with_suffix(path.suffix+'.owned.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,path)
def finalize(profile_path,output,baseline):
    profile=json.loads(Path(profile_path).read_text(encoding='utf-8-sig'))
    lab=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
    output,baseline=Path(output).absolute(),Path(baseline).absolute()
    if not output.is_relative_to(lab) or output==lab or not baseline.is_relative_to(lab):raise ValueError('CORE_NEXT_PATH_OUTSIDE_LAB')
    for ancestor in [output,*output.parents]:
        if ancestor.exists() and (ancestor.is_symlink() or getattr(ancestor.lstat(),'st_file_attributes',0)&0x400):raise ValueError('CORE_NEXT_REPARSE_PATH_REJECTED')
    verified=verify(baseline,lab)
    base=json.loads((baseline/'PAYLOAD-MANIFEST.json').read_text(encoding='utf-8-sig'))
    if profile['environment_id']=='baseline':
        for entry in base['files']:
            if entry['path'].replace('\\','/').startswith(('server/','client/')) and sha(output/entry['path'])!=entry['sha256']:
                raise ValueError('CORE_NEXT_BASELINE_ENGINE_CHANGED')
    def entries(root,excluded):
        result=[]
        for parent,dirs,files in os.walk(root,followlinks=False):
            for name in dirs+files:
                path=Path(parent)/name
                if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:raise ValueError('CORE_NEXT_REPARSE_PATH_REJECTED')
            for name in files:
                path=Path(parent)/name
                if path in excluded:continue
                result.append(dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
        return sorted(result,key=lambda row:row['path'])
    web=output/'web';web_path=web/'payload-manifest.json'
    web_manifest=json.loads((baseline/'web/payload-manifest.json').read_text(encoding='utf-8-sig'))
    web_manifest['files']=entries(web,{web_path})
    web_manifest['core_next_deployment']={'installation_id':profile['installation_id'],'source_commit':profile['source_commit'],'version':profile['version']}
    write(web_path,web_manifest)
    manifest_path=output/'PAYLOAD-MANIFEST.json';receipt_path=output/'CORE-NEXT-PAYLOAD.json'
    files=entries(output,{manifest_path,receipt_path})
    write(manifest_path,dict(schema_version=1,product=profile['product'],version=profile['version'],source_sha=profile['source_commit'],files=files))
    receipt=dict(schema_version=1,product=profile['product'],installation_id=profile['installation_id'],environment_id=profile['environment_id'],version=profile['version'],source_commit=profile['source_commit'],profile_path=str(profile_path),payload_root=str(output),baseline_payload_manifest_sha256=verified['manifest_sha256'],baseline_engine_reused=profile['environment_id']=='baseline',deployment_only_baseline_patch=profile['environment_id']=='baseline',provider_schedules_copied=False,credentials_copied=False,service_actions=False,payload_manifest_sha256=sha(manifest_path),files=len(files),completed_utc=datetime.now(timezone.utc).isoformat())
    write(receipt_path,receipt)
    return receipt
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--profile',required=True);parser.add_argument('--output',required=True);parser.add_argument('--baseline',required=True)
    args=parser.parse_args();print(json.dumps(finalize(args.profile,args.output,args.baseline),indent=2))
