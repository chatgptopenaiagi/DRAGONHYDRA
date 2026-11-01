"""Build and verify a non-editably installed wheel from a frozen source snapshot."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile


def source_ignores(source):
    """Keep the public nested dependency lock while excluding runtime state."""
    source = Path(source).resolve()
    def ignored(directory, names):
        relative = Path(directory).resolve().relative_to(source)
        blocked = {'.git', '__pycache__', 'node_modules', '.dart_tool'}
        if not relative.parts:
            blocked.update(('runtime', 'build', 'dist'))
        if relative.parts == ('config', 'runtime'):
            return [name for name in names if name != 'server-python314.lock.txt']
        return [name for name in names if name in blocked]
    return ignored


def inspect_sdist(path, build_info, lock_bytes):
    prefix = 'dragonhydra-' + build_info['python_version']
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or member.issym() or member.islnk():
                raise RuntimeError('Source archive contains an unsafe member')
            if member.isfile() and (name.suffix in ('.sqlite3', '.db', '.dpapi', '.keystore', '.jks', '.pem', '.pyc')
                                    or name.name in ('local-session.json', 'workstation.json', '.env')):
                raise RuntimeError('Source archive contains forbidden runtime state')
        embedded_lock = archive.extractfile(prefix + '/config/runtime/server-python314.lock.txt').read()
        if embedded_lock != lock_bytes:
            raise RuntimeError('Source archive dependency lock differs from frozen source')
        embedded_build = json.loads(archive.extractfile(prefix + '/src/dragonhydra/build_info.json').read())
        if embedded_build['source_sha'] != build_info['source_sha']:
            raise RuntimeError('Source archive build identity differs')
        return {'filename': path.name, 'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'members': len(archive.getmembers()),
                'dependency_lock_sha256': hashlib.sha256(embedded_lock).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--build-info',type=Path,required=True)
    parser.add_argument('--wheelhouse',type=Path,help='Existing local wheels only; disables package-index access')
    parser.add_argument('--sdist',action='store_true',help='Also build and verify the source distribution and its public dependency lock')
    args=parser.parse_args()
    source,work,assets=args.source_root.resolve(),args.work.resolve(),args.assets.resolve()
    work.mkdir(parents=True,exist_ok=True);assets.mkdir(parents=True,exist_ok=True)
    build_info=json.loads(args.build_info.read_text())
    record={'source_sha':build_info['source_sha'],'version':build_info['version'],'started_at':datetime.now(timezone.utc).isoformat(),'commands':[],'checks':[],'passed':False}
    report=work/'wheel-verification.json'
    env=os.environ.copy()
    for name in ('PYTHONPATH','PYTHONHOME','DRAGONHYDRA_HOME','VIRTUAL_ENV'):
        env.pop(name,None)
    env['PYTHONNOUSERSITE']='1';env['PIP_CACHE_DIR']=str(work/'pip-cache')
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    if args.wheelhouse:
        if not args.wheelhouse.resolve().is_dir():raise RuntimeError('Existing offline wheelhouse is unavailable')
        env['PIP_NO_INDEX']='1';env['PIP_FIND_LINKS']=str(args.wheelhouse.resolve())
        record['dependency_source']='Explicit existing local wheelhouse; package index disabled'
    def run(argv,cwd=None):
        tick=time.monotonic();r=subprocess.run(list(map(str,argv)),cwd=cwd or work,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        item={'argv':list(map(str,argv)),'exit_code':r.returncode,'duration_seconds':round(time.monotonic()-tick,3)}
        index=len(record['commands']);(work/f'command-{index}.stdout.txt').write_text(r.stdout,encoding='utf-8');(work/f'command-{index}.stderr.txt').write_text(r.stderr,encoding='utf-8')
        record['commands'].append(item)
        if r.returncode:raise RuntimeError(f'Wheel command {index} failed ({r.returncode}): '+r.stderr[-1200:])
        return r.stdout
    try:
        stage=work/'source'
        if stage.exists():raise RuntimeError('Wheel staging already exists; resume verified stage or select a fresh owned work directory')
        shutil.copytree(source,stage,ignore=source_ignores(source))
        shutil.copyfile(args.build_info,stage/'src/dragonhydra/build_info.json')
        lock=source/'config/runtime/server-python314.lock.txt'
        if not lock.is_file():raise RuntimeError('Frozen source is missing the public server dependency lock')
        if (stage/'config/runtime/server-python314.lock.txt').read_bytes()!=lock.read_bytes():raise RuntimeError('Source staging lost the public dependency lock')
        run([sys.executable,'-B','-m','build','--wheel','--no-isolation','--outdir',assets,stage])
        wheels=list(assets.glob('dragonhydra-*.whl'))
        if len(wheels)!=1:raise RuntimeError('Expected one wheel from this build')
        wheel=wheels[0]
        with ZipFile(wheel) as archive:
            names=archive.namelist()
            if any('/runtime/' in n or n.endswith(('.sqlite3','.keystore','.jks','.pem')) or '/.env' in n for n in names):raise RuntimeError('Wheel payload contains forbidden state')
            metadata=archive.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
            assert 'Requires-Python: >=3.14, <3.15' in metadata or 'Requires-Python: >=3.14,<3.15' in metadata
            assert f'Version: {build_info["python_version"]}' in metadata
            assert 'dragonhydra/resources/web/index.html' in names and 'dragonhydra/resources/web/favicon.svg' in names
            assert json.loads(archive.read('dragonhydra/build_info.json'))['source_sha']==build_info['source_sha']
            record['wheel_metadata']=metadata
            record['wheel_contents']=names
        record['checks'].append('Wheel metadata, generated tags, explicit resources, SHA and payload hygiene')
        if args.sdist:
            run([sys.executable,'-B','-m','build','--sdist','--no-isolation','--outdir',assets,stage])
            record['source_archive']=inspect_sdist(assets/('dragonhydra-'+build_info['python_version']+'.tar.gz'),build_info,lock.read_bytes())
            record['checks'].append('Source archive build identity, public dependency lock and runtime-state hygiene')
        venv=work/'installed-env';run([sys.executable,'-m','venv',venv])
        scripts=venv/('Scripts' if os.name=='nt' else 'bin');python=scripts/('python.exe' if os.name=='nt' else 'python')
        run([python,'-m','pip','install','-c',source/'config/runtime/server-python314.lock.txt',str(wheel)+'[server]'])
        run([python,'-m','pip','check'])
        outside=work/'outside-source';outside.mkdir()
        binding=json.loads(run([python,'-c','import dragonhydra,json; from dragonhydra.build_meta import info; print(json.dumps({"module":dragonhydra.__file__,"build":info()}))'],outside))
        assert Path(binding['module']).is_relative_to(venv) and 'site-packages' in Path(binding['module']).parts
        assert binding['build']['source_sha']==build_info['source_sha'];record['binding']=binding
        dragon=scripts/('dragon.exe' if os.name=='nt' else 'dragon')
        assert run([dragon,'--version'],outside).strip()==build_info['version']
        score=json.loads(run([dragon,'score','--format','json'],outside));assert score['cases']
        run([scripts/('dragonhydra-samples.exe' if os.name=='nt' else 'dragonhydra-samples'),'--directory',outside/'samples'],outside)
        db=outside/'samples.sqlite3'
        run([dragon,'import','--file',outside/'samples/examples/synthetic-market.json','--db',db,'--synthetic-clock'],outside)
        result=json.loads(run([dragon,'report','--db',db,'--event','synthetic-match-001','--cutoff','2026-01-01T12:10:00Z','--synthetic-clock','--format','json'],outside))
        assert len(result['evidence_manifest'])==18
        record['checks'].append('Fresh venv non-editable install, pip check, installed module binding, CLI sample import and JSON report outside source with PYTHONPATH cleared')
        state=outside/'server-state';log=(work/'installed-server.log').open('w',encoding='utf-8')
        proc=subprocess.Popen([str(scripts/('dragonhydra-server.exe' if os.name=='nt' else 'dragonhydra-server')),'--port','0','--state',str(state),'--init-bridge'],cwd=outside,env=env,stdout=log,stderr=subprocess.STDOUT)
        base=token=None
        def request(method,path,body=None):
            data=None if body is None else json.dumps(body).encode()
            with urlopen(Request(base+'/dragon/api/v1'+path,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method=method),timeout=15) as response:
                raw=response.read();return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
        try:
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                assert proc.poll() is None,'Installed server exited'
                try:
                    base=json.loads((state/'endpoint.json').read_text())['url'];token=json.loads((state/'local-session.json').read_text())['token']
                    if request('GET','/health/ready')['status']=='ready':break
                except (OSError,ValueError):time.sleep(.2)
            assert request('GET','/health/ready')['source_sha']==build_info['source_sha']
            with urlopen(base+'/',timeout=5) as response:assert b'DRAGONHYDRA' in response.read()
            job=request('POST','/connections/openfootball/sync',{})
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                job=request('GET','/jobs/'+job['id'])
                if job['status'] in ('succeeded','failed','cancelled'):break
                time.sleep(.2)
            assert job['status']=='succeeded',job
            assert request('GET','/matches?limit=1')['total']==760
            record['checks'].append('Installed server entry point, embedded source SHA, bundled dashboard and 760-record documented retained import')
            request('POST','/system/shutdown',{});proc.wait(timeout=20);assert proc.returncode==0
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
            log.close()
        record.update(passed=True,filename=wheel.name,bytes=wheel.stat().st_size,sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),signing='not signed; Python wheel',tags=wheel.name.rsplit('-',3)[-3:])
    finally:
        record['finished_at']=datetime.now(timezone.utc).isoformat();report.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':record['passed'],'artifact':record.get('filename'),'checks':len(record['checks']),'report':str(report)}))


if __name__=='__main__':main()
