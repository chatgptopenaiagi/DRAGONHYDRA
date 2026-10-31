"""One authenticated, schema-constrained native CPU inference with existing GGUF.

Run in a fresh private user/network namespace. The only interface is loopback;
the API key exists solely in a sealed native memfd0600 inherited by our runner.
This tests the actual R7 /completion request contract, not application API wiring.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT=Path(__file__).resolve().parents[2]
BOUNDARY=ROOT/'build/linux/local-ai-20261031'
RUNTIME=ROOT/'runtime/linux-local-ai/llama-2280f0f-cpu-r1'
MODEL=Path('/mnt/d/LocalAI/models/Qwen3-4B-Q4_K_M/Qwen3-4B-Q4_K_M.gguf')
MODEL_SHA='7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
SOURCE_DB=ROOT/'build/linux/native-kernel-20261031/provider-replay-7/run-r1/state/core.sqlite3'
PREFIX=Path('/opt/dragonhydra/api')


def digest(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=BOUNDARY/'runtime-proof-r1')
    parser.add_argument('--host-netns',required=True)
    args=parser.parse_args();work=args.work.resolve()
    if (platform.system()!='Linux' or sys.version_info[:2]!=(3,14) or not sys.flags.isolated or not sys.flags.no_site
            or work.exists() or not work.is_relative_to(BOUNDARY) or work==BOUNDARY):
        parser.error('Use native Python3.14 -I -S -B with a fresh owned evidence directory.')
    work.mkdir(parents=True)
    report={'schema_version':1,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,
            'scope':'Native CPU Qwen GGUF loading and one authenticated real retained Sports Evidence Package /completion; no application API/service integration or broader analysis claim',
            'checks':[],'model_downloaded':False,'host_network_changed':False,'operational_state_modified':False,
            'cpu_threads':4,'concurrency':1,'context_tokens':2048,'max_output_tokens':64,
            'model_executed':False,'secret_written_to_disk':False}
    tick=time.monotonic();process=None;key_fd=None;secret='';reader=None;monitor=None;stop=threading.Event();samples=[]
    def check(name,**details):
        report['checks'].append({'name':name,'passed':True,**details});print(json.dumps({'passed':name,**details}),flush=True)
    opener=build_opener(ProxyHandler({}));base=''
    def request(path,*,body=None,key=None,expected=200,timeout=3):
        headers={'Content-Type':'application/json'}
        if key is not None:headers['Authorization']='Bearer '+key
        encoded=json.dumps(body).encode() if body is not None else None
        try:response=opener.open(Request(base+path,data=encoded,headers=headers,method='POST' if body is not None else 'GET'),timeout=timeout)
        except HTTPError as error:response=error
        with response:
            payload=response.read(128*1024)
            if response.status!=expected:raise AssertionError('Unexpected runtime HTTP status '+str(response.status)+' for '+path)
            return json.loads(payload)
    try:
        namespace=os.readlink('/proc/self/ns/net');assert namespace!=args.host_netns
        subprocess.run(['/usr/sbin/ip','link','set','dev','lo','up'],check=True)
        links=json.loads(subprocess.check_output(['/usr/sbin/ip','-j','link'],text=True))
        routes=json.loads(subprocess.check_output(['/usr/sbin/ip','-j','route'],text=True))
        assert [item['ifname'] for item in links]==['lo'] and routes==[]
        with socket.socket() as probe:
            try:probe.connect(('192.0.2.1',9))
            except OSError as error:assert error.errno==errno.ENETUNREACH;denied=error.errno
            else:raise AssertionError('External routing unexpectedly available')
        report['network_isolation']={'host_namespace':args.host_netns,'private_namespace':namespace,'interfaces':['lo'],'routes':routes,'external_documentation_ip_errno':denied}
        check('Actual private network namespace denies external routing while retaining loopback')
        memory_info={line.split(':',1)[0]:int(line.split(':',1)[1].strip().split()[0]) for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line}
        cpu_model=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'unknown')
        report['hardware']={'cpu_model':cpu_model,'logical_cpus':os.cpu_count(),'memory_total_kib':memory_info['MemTotal'],
                            'memory_available_before_load_kib':memory_info['MemAvailable'],'gpu_offloading':False}
        build=json.loads((ROOT/'build/linux/local-ai-20261031/build-r1/BUILD-REPORT.json').read_text())
        identity=json.loads((RUNTIME/'BUILD-IDENTITY.json').read_text())
        assert build['passed'] and identity['passed'] and identity['binary']==build['binary']
        for item in identity['runtime_files']:
            path=RUNTIME/item['path'];assert path.is_file() and path.stat().st_size==item['bytes'] and digest(path)==item['sha256']
        binary=RUNTIME/'bin/llama-server'
        helptext=(ROOT/'build/linux/local-ai-20261031/build-r1/server-help.log').read_text()
        assert all(flag in helptext for flag in ('--offline','--api-key-file','--threads-batch','--n-gpu-layers','--ctx-size','--parallel','--port','--host'))
        check('Built ELF, private library inventory and exact supported launch flags verified',binary_sha256=digest(binary))
        assert MODEL.is_file() and MODEL.stat().st_size==2497280256
        begin=time.monotonic();model_hash=digest(MODEL);assert model_hash==MODEL_SHA
        report['model']={'filename':MODEL.name,'bytes':MODEL.stat().st_size,'sha256':model_hash,'hash_seconds':round(time.monotonic()-begin,3),'downloaded':False}
        check('Existing Qwen3-4B Q4_K_M GGUF verified byte-for-byte before loading',bytes=MODEL.stat().st_size,sha256=model_hash)
        for name in tuple(os.environ):
            if name.startswith(('DRAGONHYDRA_','LLAMA_')) or name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','HF_TOKEN','HUGGINGFACE_HUB_TOKEN'):
                os.environ.pop(name,None)
        os.environ['PYTHONTZPATH']=''
        sys.path.insert(0,str(PREFIX/'site-packages'))
        from dragonhydra.product import Product
        from dragonhydra import local_ai
        app_identity=json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        assert app_identity['source_content_sha256']=='4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
        assert Path(local_ai.__file__).resolve().is_relative_to(PREFIX/'site-packages')
        source_hash=digest(SOURCE_DB)
        state=work/'state';state.mkdir()
        with closing(sqlite3.connect(SOURCE_DB.resolve().as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(state/'core.sqlite3')) as target:
            source.backup(target)
        product=Product(state)
        selected=product.matches(provider='football-data-couk',limit=1)['items'][0]
        package=local_ai.build_package(product,selected['id']);local_ai.validate_grounding(product,package)
        body=local_ai.request_body(package);body['n_predict']=64
        assert len(body['prompt'].encode())<4096 and body['json_schema']['additionalProperties'] is False
        (work/'SPORTS-EVIDENCE-PACKAGE.json').write_text(json.dumps(package,indent=2)+'\n')
        (work/'REQUEST.json').write_text(json.dumps(body,indent=2)+'\n')
        report['evidence_package']={'match_id':selected['id'],'source_id':selected['source_id'],'evidence_id':selected['evidence_id'],'package_sha256':package['package_sha256'],'request_contract':'Actual installed R7 local_ai.request_body; only n_predict bounded from192 to64'}
        check('Actual retained football match yields validated installed R7 structured evidence request',match_id=selected['id'],source_id=selected['source_id'])
        secret=secrets.token_urlsafe(36)
        key_fd=os.memfd_create('dragonhydra-local-ai-proof-key',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        os.fchmod(key_fd,0o600);os.write(key_fd,(secret+'\n').encode());os.lseek(key_fd,0,os.SEEK_SET)
        seals=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_WRITE
        fcntl.fcntl(key_fd,fcntl.F_ADD_SEALS,seals)
        details=os.fstat(key_fd);assert stat.S_IMODE(details.st_mode)==0o600 and details.st_nlink==0 and fcntl.fcntl(key_fd,fcntl.F_GET_SEALS)==seals
        report['credential_protection']={'mechanism':'Sealed anonymous Linux memfd, inherited only by owned runner via pass_fds','mode':'0600','links':0,'sealed':True,'persistent_key_file':False,'key_in_argv':False}
        with socket.socket() as selector:selector.bind(('127.0.0.1',0));port=selector.getsockname()[1]
        base='http://127.0.0.1:'+str(port)
        argv=[str(binary),'-m',str(MODEL),'--host','127.0.0.1','--port',str(port),'--ctx-size','2048',
              '--threads','4','--threads-batch','4','--parallel','1','--n-gpu-layers','0','--offline',
              '--api-key-file','/proc/self/fd/'+str(key_fd)]
        env={**os.environ,'HOME':str(RUNTIME/'home'),'XDG_CACHE_HOME':str(RUNTIME/'cache'),'TMPDIR':str(RUNTIME/'scratch'),
             'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1'}
        process=subprocess.Popen(argv,cwd=work,env=env,pass_fds=(key_fd,),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 text=True,encoding='utf-8',errors='replace',start_new_session=True)
        report['runner']={'pid':process.pid,'url':base,'argv':argv,'binary_sha256':digest(binary)}
        def logs():
            with (work/'runner.log').open('w') as output:
                for line in process.stdout:
                    output.write(line.replace(secret,'[REDACTED]'));output.flush()
        reader=threading.Thread(target=logs,daemon=True);reader.start()
        def memory():
            while not stop.wait(.1):
                try:
                    values={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/'+str(process.pid)+'/status').read_text().splitlines() if ':' in line}
                    samples.append({key:int(values[key].split()[0]) for key in ('VmRSS','VmHWM','Threads') if key in values})
                except (FileNotFoundError,ProcessLookupError):break
        monitor=threading.Thread(target=memory,daemon=True);monitor.start()
        load_started=time.monotonic();deadline=load_started+180
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Owned llama-server exited during loading: '+str(process.returncode))
            try:
                health=request('/health',timeout=2)
                if health.get('status')=='ok':break
            except (URLError,OSError,AssertionError):pass
            time.sleep(.2)
        else:raise RuntimeError('Bounded180s model startup deadline exceeded')
        report['model_executed']=True
        report['load_ready_seconds']=round(time.monotonic()-load_started,3)
        check('Native CPU model loads and loopback health becomes ready',seconds=report['load_ready_seconds'])
        properties=request('/props',key=secret)
        template=properties.get('chat_template')
        assert isinstance(template,str) and '<|im_start|>' in template and '<|im_end|>' in template
        assert properties['default_generation_settings']['n_ctx']==2048 and properties['total_slots']==1
        report['model_runtime_metadata']={'model_alias':properties.get('model_alias'),'model_ftype':properties.get('model_ftype'),
            'chat_template_sha256':hashlib.sha256(template.encode()).hexdigest(),'chat_template_bytes':len(template.encode()),
            'qwen_role_markers_verified':True,'context_tokens':properties['default_generation_settings']['n_ctx'],
            'concurrency_slots':properties['total_slots'],'build_info':properties.get('build_info')}
        check('Loaded GGUF exposes compatible Qwen role template,2048-token context and one slot')
        request('/completion',body=body,expected=401)
        request('/completion',body=body,key='invalid-labelled-proof-key',expected=401)
        check('Unauthenticated and incorrect-key completion calls are rejected before generation')
        begin=time.monotonic();response=request('/completion',body=body,key=secret,timeout=65)
        report['completion_seconds']=round(time.monotonic()-begin,3)
        accepted=local_ai.validate_output(package,response['content']);local_ai.validate_grounding(product,package)
        assert accepted['kind']=='local_llm' and accepted['mode']=='constrained_source_fact_selection'
        assert response.get('tokens_predicted',65)<=64
        assert accepted['evidence_id']==selected['evidence_id'] and accepted['source_sha256']==package['evidence']['E1']['source_sha256']
        (work/'RESPONSE.json').write_text(json.dumps(response,indent=2)+'\n')
        (work/'VALIDATED-FINDING.json').write_text(json.dumps(accepted,indent=2)+'\n')
        report['validated_finding']=accepted
        report['timings']=response.get('timings',{})
        report['generated_tokens']=response.get('tokens_predicted')
        check('Actual authenticated /completion returns schema-valid cited source-fact selection',seconds=report['completion_seconds'],tokens=report['generated_tokens'],evidence_id=accepted['evidence_id'])
        assert digest(SOURCE_DB)==source_hash,'Original retained data changed'
        assert digest(MODEL)==MODEL_SHA,'Model changed during proof'
        assert all(digest(RUNTIME/item['path'])==item['sha256'] for item in identity['runtime_files'])
        report['inputs_unchanged']=True
        report['passed']=True
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error).replace(secret,'[REDACTED]') if secret else str(error),'line':traceback.extract_tb(error.__traceback__)[-1].lineno}
        (work/'traceback.log').write_text(traceback.format_exc().replace(secret,'[REDACTED]') if secret else traceback.format_exc())
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    assert Path('/proc/'+str(process.pid)+'/exe').resolve()==(RUNTIME/'bin/llama-server').resolve()
                    process.terminate()
                    try:process.wait(timeout=25)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
                report['runner_exit_code']=process.returncode
                report['runner_reaped']=True
            except Exception as error:
                report['passed']=False;report['cleanup_error']=type(error).__name__+': '+str(error)
        stop.set()
        for thread in (monitor,reader):
            if thread is not None:thread.join(timeout=3)
        if key_fd is not None:os.close(key_fd);report['anonymous_key_closed']=True
        if samples:
            report['memory']={'peak_observed_rss_kib':max(s.get('VmRSS',0) for s in samples),
                              'peak_process_hwm_kib':max(s.get('VmHWM',0) for s in samples),'max_process_threads':max(s.get('Threads',0) for s in samples),'samples':len(samples)}
        report['limitation']='The model selects one supplied retained fact and E1. It does not generate new sports investigations, forecasts or probability arithmetic. API integration is a later step.'
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),seconds=round(time.monotonic()-tick,3))
        report['exit_code']=0 if report['passed'] else 1
        (work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':report['passed'],'seconds':report['seconds'],'model_executed':report['model_executed'],
                          'runner_exit_code':report.get('runner_exit_code'),'error':report.get('error'),
                          'evidence':(work/'verification.json').relative_to(ROOT).as_posix()}),flush=True)
    return report['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
