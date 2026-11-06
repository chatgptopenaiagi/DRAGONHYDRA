"""Curate a deterministic development ZIP from one clean, committed Git tree.

No install, dependency download, application execution or publication occurs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

# Import the new server policy only; no service, state or server is started.
sys.path.insert(0,str(Path(__file__).absolute().parents[1]/'src'))
from dragonhydra.future_relevance.server import package_member_allowed

VERSION = '0.2.0-virtual-experimental'
PREFIX = 'GENESIS-6.1-FUTURE-RELEVANCE/source/'
BUILD = 'GENESIS61-BUILD.json'
MANIFEST = 'GENESIS61-PAYLOAD.json'
GIT = r'C:\Program Files\Git\cmd\git.exe'
WEB = {'app.js','index.html','style.css','favicon.svg','realtime.js','realtime.css','future.js','future.css'}
REQUIRED = {'src/dragonhydra/api.py','src/dragonhydra/product.py','src/dragonhydra/kernel/composition.py',
            'scripts/Start-Genesis61.ps1','scripts/build_genesis61.py','docs/future-relevance/DASHBOARD.md'}
REQUIRED |= {f'src/dragonhydra/{package}/{name}.py' for package in ('realtime','future_relevance')
             for name in ('__init__','server','router','service')}
REQUIRED |= {'src/dragonhydra/resources/web/'+name for name in WEB}
curated = package_member_allowed


def need(condition, code):
    if not condition: raise ValueError(code)


def encoded(value): return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode('utf-8')


def package_bytes(source_sha, entries, commit_time):
    """Pure formatter; production caller supplies only validated Git blob bytes."""
    need(re.fullmatch('[a-f0-9]{40}', source_sha), 'FULL_COMMITTED_SOURCE_REQUIRED')
    need(type(commit_time) is int and commit_time > 0, 'COMMIT_TIMESTAMP_REQUIRED')
    need(REQUIRED <= entries.keys() and all(curated(name) for name in entries), 'CURATED_REQUIRED_FILES_MISMATCH')
    need(len(entries)<=1000 and len({name.casefold() for name in entries})==len(entries), 'PAYLOAD_COUNT_OR_CASE_COLLISION')
    need(all(isinstance(raw,bytes) and len(raw)<=4*1024*1024 for raw in entries.values())
         and sum(map(len,entries.values()))<=64*1024*1024, 'PAYLOAD_SIZE_BOUND')
    tree=ast.parse(entries['src/dragonhydra/future_relevance/__init__.py'].decode('utf-8'))
    versions=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets)]
    need(versions==[VERSION], 'COMPONENT_VERSION_MISMATCH')
    files=[{'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'git_blob_sha1':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
           for name,raw in sorted(entries.items())]
    manifest=encoded({'schema_version':'dragonhydra.genesis61-payload/1','source_sha':source_sha,
                      'component_version':VERSION,'files':files})
    need(len(manifest)<=256*1024,'MANIFEST_SIZE_BOUND')
    build=encoded({'schema_version':'dragonhydra.genesis61-build/1','source_sha':source_sha,
        'component_version':VERSION,'source_clean':True,'commit_time_unix':commit_time,
        'package_prefix':PREFIX,'payload_manifest':MANIFEST,
        'payload_manifest_sha256':hashlib.sha256(manifest).hexdigest(),'payload_files':len(files),
        'synthetic_only':True,'real_sporting_data_included':False,'runtime_or_credentials_included':False,
        'dependencies_included':False,'build_kind':'curated-virtual-development-source'})
    members={**entries,BUILD:build,MANIFEST:manifest}
    output=io.BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as archive:
        for name,raw in sorted(members.items()):
            info=ZipInfo(PREFIX+name,(1980,1,1,0,0,0));info.create_system=3
            info.external_attr=0o100644<<16;info.compress_type=ZIP_DEFLATED
            archive.writestr(info,raw,compress_type=ZIP_DEFLATED,compresslevel=9)
    return output.getvalue(),json.loads(build)


def committed_payload(source, source_sha):
    def git(*args):
        result=subprocess.run([GIT,'--no-optional-locks','-C',str(source),*args],capture_output=True,timeout=60)
        need(result.returncode==0,'GIT_READ_FAILED');return result.stdout
    need(source.is_dir() and re.fullmatch('[a-f0-9]{40}',source_sha),'REGISTERED_SOURCE_COMMIT_REQUIRED')
    need(Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()==source.resolve(),'EXACT_GIT_SOURCE_ROOT_REQUIRED')
    need(git('rev-parse','HEAD').decode().strip()==source_sha and not git('status','--porcelain').strip(),'CLEAN_COMMITTED_SOURCE_REQUIRED')
    entries={}
    for record in git('ls-tree','-rz','--full-tree',source_sha).split(b'\0'):
        if not record:continue
        meta,raw_path=record.split(b'\t',1);mode,kind,oid=meta.split();name=raw_path.decode('utf-8')
        if not curated(name):continue
        need(mode==b'100644' or mode==b'100755','LINKED_OR_NONFILE_PAYLOAD_REJECTED')
        need(kind==b'blob','GIT_BLOB_REQUIRED')
        raw=git('cat-file','blob',oid.decode())
        need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid.decode(),'GIT_BLOB_CONTENT_MISMATCH')
        entries[name]=raw
    need(not git('status','--porcelain').strip() and git('rev-parse','HEAD').decode().strip()==source_sha,'SOURCE_CHANGED_DURING_COLLECTION')
    return entries,int(git('show','-s','--format=%ct',source_sha).decode().strip())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).absolute().parents[1])
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    source=args.source_root.absolute();output=args.output.absolute()
    need(source.name=='source' and source.parent.name=='GENESIS-6.1-FUTURE-RELEVANCE','EXACT_GENESIS61_SOURCE_LANE_REQUIRED')
    need('..' not in source.parts and '..' not in output.parts,'PARENT_TRAVERSAL_REJECTED')
    for part in (source,*source.parents):
        need(not part.is_symlink() and not getattr(part.lstat(),'st_file_attributes',0)&0x400,'REPARSE_SOURCE_REJECTED')
    need(not output.is_relative_to(source),'OUTPUT_MUST_STAY_OUTSIDE_SOURCE')
    need(output.suffix=='.zip' and not output.exists(),'NEW_ZIP_OUTPUT_REQUIRED')
    sidecar=output.with_suffix('.zip.sha256')
    need(not sidecar.exists() and not sidecar.is_symlink(),'NEW_SIDECAR_REQUIRED')
    need(output.parent.is_dir(),'EXISTING_OUTPUT_DIRECTORY_REQUIRED')
    for part in (output.parent,*output.parent.parents):
        need(not part.is_symlink() and not getattr(part.lstat(),'st_file_attributes',0)&0x400,'REPARSE_OUTPUT_REJECTED')
    entries,commit_time=committed_payload(source,args.source_commit)
    raw,build=package_bytes(args.source_commit,entries,commit_time)
    with output.open('xb') as stream:
        stream.write(raw);stream.flush()
        import os
        os.fsync(stream.fileno())
    receipt={'path':str(output),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
             'source_sha':args.source_commit,'component_version':VERSION,'payload_files':build['payload_files'],
             'runtime_executed':False,'dependencies_downloaded':False}
    with sidecar.open('x',encoding='ascii') as stream:stream.write(receipt['sha256']+'  '+output.name+'\n')
    print(json.dumps(receipt,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
