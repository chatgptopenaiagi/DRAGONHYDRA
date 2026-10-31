"""Build only a CPU llama-server from the registered read-only local source.

All source copies, objects, logs and staged libraries stay in this project.
Run inside a private user/network namespace; no dependency/model download or
installation is performed. The source commit is recorded only after clean-tree
and exact selected-content checks. The original source/build is never changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import subprocess
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path('/home/love/AI-LAB/diagnostics/genesis-1.5/llama.cpp')
COMMIT='2280f0fd163b03d4331d49e08460f66502e35854'
BUILD_ROOT=ROOT/'build/linux/local-ai-20261031'
RUNTIME_ROOT=ROOT/'runtime/linux-local-ai'
FLAGS={
    'CMAKE_BUILD_TYPE':'Release','BUILD_SHARED_LIBS':'ON',
    'CMAKE_BUILD_RPATH_USE_ORIGIN':'ON','CMAKE_INSTALL_RPATH':'$ORIGIN',
    'LLAMA_BUILD_COMMON':'ON','LLAMA_BUILD_TOOLS':'ON','LLAMA_BUILD_SERVER':'ON',
    'LLAMA_BUILD_TESTS':'OFF','LLAMA_BUILD_EXAMPLES':'OFF','LLAMA_BUILD_APP':'OFF',
    'LLAMA_BUILD_UI':'OFF','LLAMA_USE_PREBUILT_UI':'OFF','LLAMA_CONNECT':'OFF',
    'LLAMA_OPENSSL':'OFF','LLAMA_SUBPROCESS':'OFF','LLAMA_LLGUIDANCE':'OFF',
    'LLAMA_BUILD_BORINGSSL':'OFF','LLAMA_BUILD_LIBRESSL':'OFF',
    'GGML_CPU':'ON','GGML_NATIVE':'OFF','GGML_BLAS':'OFF',
    'GGML_CUDA':'OFF','GGML_HIP':'OFF','GGML_VULKAN':'OFF','GGML_METAL':'OFF',
    'GGML_WEBGPU':'OFF','GGML_SYCL':'OFF','GGML_OPENCL':'OFF','GGML_HEXAGON':'OFF',
    'GGML_ZENDNN':'OFF','GGML_RPC':'OFF','GGML_CPU_KLEIDIAI':'OFF',
    'GGML_OPENMP_FETCH':'OFF','FETCHCONTENT_FULLY_DISCONNECTED':'ON',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=BUILD_ROOT/'build-r1')
    parser.add_argument('--runtime',type=Path,default=RUNTIME_ROOT/'llama-2280f0f-cpu-r1')
    parser.add_argument('--host-netns',required=True)
    parser.add_argument('--resume-configured',action='store_true',help='Resume only the saved preflight stop before compilation, after exact source/cache validation')
    args=parser.parse_args();work=args.work.resolve();runtime=args.runtime.resolve()
    if (platform.system()!='Linux' or platform.machine()!='x86_64'
            or not work.is_relative_to(BUILD_ROOT) or work==BUILD_ROOT
            or not runtime.is_relative_to(RUNTIME_ROOT) or runtime==RUNTIME_ROOT):
        parser.error('Use fresh owned build/runtime directories on the verified Linux x86_64 target.')
    previous=None
    if args.resume_configured:
        if not work.is_dir() or not runtime.is_dir() or not (work/'BUILD-REPORT.json').is_file():
            parser.error('No saved configured candidate to resume.')
        previous=json.loads((work/'BUILD-REPORT.json').read_text())
        if (previous.get('passed') or previous.get('error',{}).get('message')!='CMake reported unused flags; inspect before building'
                or (work/'compile.log').exists() or (runtime/'bin').exists() or (work/'BUILD-REPORT.initial.json').exists()):
            parser.error('Only the exact retained preflight stop may be resumed once.')
        shutil.copyfile(work/'BUILD-REPORT.json',work/'BUILD-REPORT.initial.json')
    elif work.exists() or runtime.exists():
        parser.error('Preserve existing build/runtime evidence; select fresh directories.')
    work.mkdir(parents=True,exist_ok=args.resume_configured);runtime.mkdir(parents=True,exist_ok=args.resume_configured)
    report={'schema_version':1,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,
            'scope':'Native CPU llama-server component only; no application integration/model inference/installation claim',
            'source_path':str(SOURCE),'commands':[],'model_downloaded':False,'dependencies_installed':False,
            'original_source_modified':False,'profile':'CPU, four build workers; GPU backends disabled'}
    tick=time.monotonic();manifest=[]
    if previous:
        report['resumed_from']='BUILD-REPORT.initial.json'
        report['retained_initial_failure']=previous['error']
    env={**os.environ,'HOME':str(runtime/'home'),'XDG_CACHE_HOME':str(runtime/'cache'),
         'TMPDIR':str(runtime/'scratch'),'GIT_CEILING_DIRECTORIES':str(work),
         'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'}
    for folder in ('home','cache','scratch'):(runtime/folder).mkdir(exist_ok=args.resume_configured)
    def run(name,argv,timeout=90):
        begin=time.monotonic()
        with (work/(name+'.log')).open('w') as log:
            result=subprocess.run(list(map(str,argv)),cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':result.returncode,'seconds':round(time.monotonic()-begin,3)})
        if result.returncode:raise RuntimeError(name+' failed exit'+str(result.returncode)+'; inspect project build log')
        return (work/(name+'.log')).read_text()
    def git(*args):
        return subprocess.check_output(['/usr/bin/git','-C',str(SOURCE),*args],env=env,text=True).strip()
    try:
        namespace=os.readlink('/proc/self/ns/net');assert namespace!=args.host_netns
        subprocess.run(['/usr/sbin/ip','link','set','dev','lo','up'],check=True)
        interfaces=json.loads(subprocess.check_output(['/usr/sbin/ip','-j','link'],text=True))
        routes=json.loads(subprocess.check_output(['/usr/sbin/ip','-j','route'],text=True))
        assert [item['ifname'] for item in interfaces]==['lo'] and routes==[]
        with socket.socket() as probe:
            try:probe.connect(('192.0.2.1',9))
            except OSError as error:assert error.errno==errno.ENETUNREACH;denied=error.errno
            else:raise RuntimeError('Private network namespace unexpectedly has an external route')
        report['network_isolation']={'host_namespace':args.host_netns,'private_namespace':namespace,
                                     'interfaces':['lo'],'routes':routes,'documentation_ip_probe_errno':denied}
        report['tools']=previous['tools'] if previous else {name:run(name,[path,'--version']).splitlines()[0] for name,path in
                         (('cmake','/usr/bin/cmake'),('compiler','/usr/bin/c++'),('make','/usr/bin/make'))}
        commit=git('rev-parse','HEAD');assert commit==COMMIT
        assert git('status','--porcelain','--untracked-files=no')=='','Registered upstream tracked source is not clean'
        build_number=git('rev-list','--count','HEAD')
        names=subprocess.check_output(['/usr/bin/git','-C',str(SOURCE),'ls-files','-z'],env=env).decode().split('\0')
        roots={'cmake','common','ggml','include','src','tools','vendor'}
        fixed={'CMakeLists.txt','LICENSE','AUTHORS','README.md','scripts/ui-assets.cmake'}
        selected=sorted(name for name in names if name and (PurePosixPath(name).parts[0] in roots or name in fixed))
        source=work/'source';source.mkdir(exist_ok=args.resume_configured)
        retained_manifest=json.loads((work/'SOURCE-MANIFEST.json').read_text()) if previous else None
        for name in selected:
            relative=PurePosixPath(name);assert not relative.is_absolute() and '..' not in relative.parts
            origin=SOURCE/name;assert origin.is_file() and not origin.is_symlink(),'Missing/linked selected upstream source: '+name
            body=origin.read_bytes();target=source/name
            if not previous:
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
            assert sha(target)==hashlib.sha256(body).hexdigest()
            manifest.append({'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
        fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        report['source']={'commit':commit,'tracked_source_clean_before':True,'selected_files':len(manifest),
                          'selected_bytes':sum(i['bytes'] for i in manifest),'content_sha256':fingerprint,
                          'selection':'Tracked build roots cmake/common/ggml/include/src/tools/vendor, root build/license metadata and UI CMake helper; no .git, model weights, existing builds, untracked/private files.'}
        if previous:
            assert retained_manifest=={'schema_version':1,'commit':commit,'content_sha256':fingerprint,'files':manifest},'Saved source snapshot changed before resume'
        else:
            (work/'SOURCE-MANIFEST.json').write_text(json.dumps({'schema_version':1,'commit':commit,'content_sha256':fingerprint,'files':manifest},indent=2)+'\n')
        print(json.dumps({'stage':'source_copied','files':len(manifest),'bytes':report['source']['selected_bytes'],'source_content_sha256':fingerprint}),flush=True)
        flags={**FLAGS,'LLAMA_BUILD_COMMIT':commit,'LLAMA_BUILD_NUMBER':build_number}
        configured=(work/'configure.log').read_text() if previous else run('configure',['/usr/bin/cmake','-S',source,'-B',work/'objects','-G','Unix Makefiles',*[f'-D{k}={v}' for k,v in flags.items()]],timeout=180)
        if 'Manually-specified variables were not used by the project' in configured:
            tail=configured.split('Manually-specified variables were not used by the project:',1)[1]
            unused=re.findall(r'^    ([A-Z][A-Z0-9_]*)\s*$',tail,re.MULTILINE)
            if unused!=['FETCHCONTENT_FULLY_DISCONNECTED']:
                raise RuntimeError('CMake reported unexpected unused flags; inspect before building')
            report['unused_standard_guard']={'variable':unused[0],'reason':'No optional dependency FetchContent branch was enabled; private network namespace independently denies all outbound routes.'}
        if previous:
            cache={}
            for line in (work/'objects/CMakeCache.txt').read_text().splitlines():
                if ':' in line and '=' in line and not line.startswith(('#','//')):
                    key,value=line.split('=',1);cache[key.split(':',1)[0]]=value
            assert all(cache.get(key)==value for key,value in flags.items()),'Saved CMake cache differs from reviewed CPU/offline configuration'
        report['cmake_flags']=flags
        print(json.dumps({'stage':'configured','target':'llama-server','build_workers':4}),flush=True)
        run('compile',['/usr/bin/cmake','--build',work/'objects','--target','llama-server','--parallel','4'],timeout=1800)
        binary=work/'objects/bin/llama-server';assert binary.read_bytes()[:4]==b'\x7fELF'
        target_bin=runtime/'bin';target_bin.mkdir()
        for entry in sorted(binary.parent.iterdir()):
            destination=target_bin/entry.name
            if entry.is_symlink():
                link=os.readlink(entry);assert '/' not in link and entry.resolve().is_relative_to(binary.parent)
                destination.symlink_to(link)
            elif entry.is_file():shutil.copy2(entry,destination)
            else:raise RuntimeError('Unexpected directory in target runtime bin')
        notices=runtime/'notices';notices.mkdir()
        for item in manifest:
            path=Path(item['path'])
            if path.name.lower() in ('license','license.txt','license.md','copying','notice','notice.txt','authors'):
                dest=notices/item['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/item['path'],dest)
        for entry in (work/'objects').rglob('*license*.h'):
            if entry.is_file():shutil.copyfile(entry,notices/entry.name)
        version=run('server-version',[target_bin/'llama-server','--version'])
        helptext=run('server-help',[target_bin/'llama-server','--help'])
        required=('--offline','--api-key-file','--json-schema','--chat-template','--threads','--ctx-size','--parallel','--host','--port')
        assert all(flag in helptext for flag in required),'Built runtime lacks required supported options'
        elf=run('elf',['/usr/bin/readelf','-h',target_bin/'llama-server'])
        dynamic=run('dynamic',['/usr/bin/readelf','-d',target_bin/'llama-server'])
        libraries=run('libraries',['/usr/bin/ldd',target_bin/'llama-server'])
        assert 'not found' not in libraries and 'X86-64' in elf
        assert str(SOURCE) not in libraries and str(work/'objects') not in libraries,'Runtime still resolves libraries from development builds'
        assert COMMIT in version and 'GNU 15.2.0' in version
        assert all(sha(SOURCE/item['path'])==item['sha256'] and sha(source/item['path'])==item['sha256'] for item in manifest),'UPSTREAM_OR_SNAPSHOT_CHANGED'
        assert git('rev-parse','HEAD')==COMMIT and git('status','--porcelain','--untracked-files=no')==''
        report['source'].update(tracked_source_clean_after=True,all_selected_hashes_unchanged=True)
        inventory=[{'path':p.relative_to(runtime).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(runtime.rglob('*')) if p.is_file() and not p.is_symlink() and not any(part in ('home','cache','scratch') for part in p.relative_to(runtime).parts)]
        report.update(passed=True,runtime=runtime.relative_to(ROOT).as_posix(),binary={'path':'bin/llama-server','bytes':(target_bin/'llama-server').stat().st_size,'sha256':sha(target_bin/'llama-server')},
                      runtime_files=inventory,version=version.strip(),required_help_flags_verified=list(required),
                      elf_verified=True,shared_libraries_verified=True,notices_retained=True,
                      limitation='CPU runtime built/tested on this Ubuntu26.04 x86_64 machine only; model inference and API integration are separate verification stages.')
        (runtime/'BUILD-IDENTITY.json').write_text(json.dumps(report,indent=2)+'\n')
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'line':traceback.extract_tb(error.__traceback__)[-1].lineno}
        (work/'traceback.log').write_text(traceback.format_exc())
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),seconds=round(time.monotonic()-tick,3))
        (work/'BUILD-REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':report['passed'],'seconds':report['seconds'],'binary':report.get('binary'),'error':report.get('error'),'report':(work/'BUILD-REPORT.json').relative_to(ROOT).as_posix()}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
