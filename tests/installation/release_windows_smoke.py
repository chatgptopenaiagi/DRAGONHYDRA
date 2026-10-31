"""Exercise exact release ZIP/client bytes with isolated state and WebView data.

The live product launcher, Joomla, gateway, VPN, databases and browser profile
are never used. Full evidence is local; publication consumes a sanitized summary.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile
from xml.etree import ElementTree as ET

API='/dragon/api/v1'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--server-archive',required=True,type=Path)
    parser.add_argument('--client-binary',required=True,type=Path)
    parser.add_argument('--installer',type=Path)
    parser.add_argument('--work-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--skip-native',action='store_true')
    args=parser.parse_args()
    args.work_root=args.work_root.resolve()
    args.work_root.mkdir(parents=True,exist_ok=True)
    args.output=args.output.resolve()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    run=args.work_root/('windows-verify-'+uuid4().hex)
    run.mkdir()
    checks=[]
    record={'schema_version':1,'started_at':datetime.now(timezone.utc).isoformat(),
            'source_sha':args.source_sha,'version':args.version,'work':str(run),
            'checks':checks,'passed':False,'clean_machine_tested':False,
            'scope':'Isolated exact packaged Windows client/server on this host; no working service modified'}
    proc=None
    log=None
    base=None
    token=None
    env=os.environ.copy()
    for name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):
        env.pop(name,None)
    system=os.environ.get('SystemRoot',r'C:\Windows')
    env['PATH']=str(Path(system)/'System32')+os.pathsep+system
    extracted=run/'extracted'
    extracted.mkdir()

    def call(method,path,body=None,auth=True,wrong=False,key=None):
        headers={'Content-Type':'application/json'}
        if auth:
            headers['Authorization']='Bearer '+('rejected-release-test-token' if wrong else token)
        if key:
            headers['Idempotency-Key']=key
        raw=None if body is None else json.dumps(body).encode()
        try:
            with urlopen(Request(base+path,raw,headers,method=method),timeout=15) as response:
                content=response.read()
                return response.status,json.loads(content) if 'json' in response.headers.get('Content-Type','') else content
        except HTTPError as exc:
            return exc.code,json.loads(exc.read())

    def wait_job(job_id):
        until=time.monotonic()+60
        while time.monotonic()<until:
            code,result=call('GET',API+'/jobs/'+job_id)
            assert code==200,result
            if result['status']=='succeeded':
                return result
            assert result['status'] not in ('failed','cancelled'),result
            time.sleep(.15)
        raise AssertionError('Test-owned packaged worker job did not finish')

    def start():
        nonlocal proc,base,token,log
        log=(run/('server-'+uuid4().hex+'.log')).open('w',encoding='utf-8')
        proc=subprocess.Popen([str(server),'--host','127.0.0.1','--port','0','--state',str(state)],
                              cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        until=time.monotonic()+30
        while time.monotonic()<until:
            assert proc.poll() is None,'Packaged server exited during startup'
            try:
                base=json.loads((state/'endpoint.json').read_text())['url']
                token=json.loads((state/'local-session.json').read_text())['token']
                code,data=call('GET',API+'/health/ready')
                if code==200:
                    assert data['version']==args.version,data
                    assert data.get('source_sha')==args.source_sha,data
                    return
            except (OSError,ValueError):
                pass
            time.sleep(.2)
        raise AssertionError('Packaged server readiness deadline exceeded')

    def stop():
        nonlocal proc,log
        assert call('POST',API+'/system/shutdown',{})[0]==200
        proc.wait(timeout=20)
        assert proc.returncode==0,proc.returncode
        log.close()
        log=None

    def native(binary,client_state,mode,name,server_state=None):
        output=run/(name+'.json')
        script=Path(__file__).with_name('release_native_uia.ps1')
        command=[r'C:\Program Files\PowerShell\7\pwsh.exe','-NoLogo','-NoProfile','-File',str(script),
                 '-Binary',str(binary),'-State',str(client_state),'-Output',str(output),'-Mode',mode]
        if server_state:
            command+=['-ServerState',str(server_state)]
        completed=subprocess.run(command,cwd=run,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
        (run/(name+'.log')).write_text(completed.stdout,encoding='utf-8')
        assert completed.returncode==0,completed.stdout[-1500:]
        data=json.loads(output.read_text(encoding='utf-8-sig'))
        assert data['passed'] and data.get('clean_exit'),data
        return {'name':name,'passed':True,'native_groups':len(data['checks']),'evidence':str(output)}

    try:
        record['server_archive']={'filename':args.server_archive.name,'sha256':hashlib.sha256(args.server_archive.read_bytes()).hexdigest()}
        with ZipFile(args.server_archive) as archive:
            for member in archive.infolist():
                destination=(extracted/member.filename).resolve()
                assert destination.is_relative_to(extracted.resolve()),'Archive path escaped extraction root'
                assert not (member.external_attr>>16)&0o170000==0o120000,'Symlink in release payload'
            archive.extractall(extracted)
        candidates=list(extracted.rglob('DRAGONHYDRA-Server.exe'))
        assert len(candidates)==1,'Server ZIP must contain one complete server executable'
        server=candidates[0]
        assert (server.parent/'_internal'/'python314.dll').is_file(),'Private Python314 runtime absent'
        build_probe=subprocess.run([str(server),'--build-info'],cwd=run,env=env,capture_output=True,text=True,timeout=20)
        assert build_probe.returncode==0,build_probe.stderr
        data=json.loads(build_probe.stdout)
        assert data['source_sha']==args.source_sha and data['version']==args.version,data
        record['server_build_info']=data
        client_probe=subprocess.run([str(args.client_binary.resolve()),'--build-info'],cwd=run,capture_output=True,text=True,timeout=20)
        assert client_probe.returncode==0,client_probe.stderr
        client_info=json.loads(client_probe.stdout)
        assert client_info['source_sha']==args.source_sha and client_info['version']==args.version,client_info
        record['client_build_info']=client_info
        checks.append({'name':'extracted-private-runtime-and-both-compiled-source-identities','passed':True})
        state=run/'server-state'
        state.mkdir()
        start()
        assert call('GET',API+'/health/ready',auth=False)[0]==401
        assert call('GET',API+'/health/ready',wrong=True)[0]==401
        assert call('POST',API+'/session',{'token':'\u65e5'*25},auth=False)[0]==401
        checks.append({'name':'packaged-authentication-rejection-and-unicode-regression','passed':True})
        code,job=call('POST',API+'/connections/openfootball/sync',{},key='release-offline-import')
        assert code==202,job
        imported=wait_job(job['id'])
        assert imported['result']['record_count']==760,imported
        assert call('POST',API+'/connections/openfootball/sync',{},key='release-offline-import')[1]['id']==job['id']
        code,matches=call('GET',API+'/matches?limit=1')
        selected=matches['items'][0]
        assert call('GET',API+'/matches/'+selected['id'])[1]['id']==selected['id']
        assert call('GET',API+'/teams/'+selected['home']['id'])[0]==200
        assert call('GET',API+'/competitions/'+selected['competition_id']+'/standings')[0]==200
        assert call('GET',API+'/matches/'+selected['id']+'/odds')[1]['items']==[]
        checks.append({'name':'packaged-import-and-canonical-context-with-explicit-missing-odds','passed':True,'records':760,'match_id':selected['id']})
        if not args.skip_native:
            unpaired=run/'unpaired-state'
            unpaired.mkdir()
            checks.append(native(args.client_binary.resolve(),unpaired,'unpaired','first-run-native',state))
            rejected=run/'rejected-state'
            rejected.mkdir()
            shutil.copyfile(state/'endpoint.json',rejected/'endpoint.json')
            (rejected/'local-session.json').write_text(json.dumps({'token':'this-is-an-invalid-test-token-1234567890'}),encoding='utf-8')
            checks.append(native(args.client_binary.resolve(),rejected,'rejected','rejected-native',state))
            checks.append(native(args.client_binary.resolve(),state,'journey','portable-native'))
        exports=list((state/'exports').glob('*.xlsx'))
        if args.skip_native:
            code,job=call('POST',API+'/exports',{'match_id':selected['id'],'format':'xlsx'})
            assert code==202
            result=wait_job(job['id'])
            exports=[state/'exports'/result['result']['filename']]
        assert exports,'Native export control did not produce a workbook'
        with ZipFile(exports[-1]) as book:
            workbook=ET.fromstring(book.read('xl/workbook.xml'))
            sheets=[n.attrib['name'] for n in workbook.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/*')]
            assert sheets==['Match','Metadata'],sheets
            assert selected['id'].encode() in book.read('xl/worksheets/sheet1.xml')
        checks.append({'name':'native-triggered-workbook-final-bytes-verified' if not args.skip_native else 'api-workbook-final-bytes-verified','passed':True,'bytes':exports[-1].stat().st_size,'sha256':hashlib.sha256(exports[-1].read_bytes()).hexdigest()})
        old_token=token
        stop()
        if not args.skip_native:
            # The prior endpoint is now actually unavailable; the native shell
            # must offer the connection dialog instead of an empty error webview.
            offline=run/'unavailable-state'
            offline.mkdir()
            (offline/'endpoint.json').write_text(json.dumps({'url':base}),encoding='utf-8')
            (offline/'local-session.json').write_text(json.dumps({'token':old_token}),encoding='utf-8')
            checks.append(native(args.client_binary.resolve(),offline,'unpaired','unavailable-native'))
        start()
        assert token==old_token,'Restart lost test pairing'
        assert call('GET',API+'/matches?limit=1')[1]['total']==760,'Restart lost imported records'
        assert call('GET',API+'/matches/'+selected['id'])[1]['id']==selected['id']
        checks.append({'name':'packaged-restart-retains-settings-pairing-and-data','passed':True,'records':760})
        if args.installer:
            installer_script=Path(__file__).with_name('release_client_install.ps1')
            output=run/'installed-client.json'
            install_command=[r'C:\Program Files\PowerShell\7\pwsh.exe','-NoLogo','-NoProfile','-File',str(installer_script),
                             '-Installer',str(args.installer.resolve()),'-State',str(state),'-Output',str(output),'-WorkRoot',str(run)]
            completed=subprocess.run(install_command,cwd=run,capture_output=True,text=True,timeout=240)
            (run/'installed-client.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
            assert completed.returncode==0,completed.stdout[-1500:]+completed.stderr[-1500:]
            installation=json.loads(output.read_text(encoding='utf-8-sig'))
            assert installation['passed'],installation
            checks.append({'name':'exact-nsis-install-native-journey-uninstall-retained-server','passed':True,'evidence':str(output)})
        stop()
        record['passed']=True
    except Exception as exc:
        record['error']=f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if proc and proc.poll() is None:
            try:
                stop()
            except Exception:
                proc.terminate()
                proc.wait(timeout=10)
        if log:
            log.close()
        record['finished_at']=datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(record,indent=2))


if __name__=='__main__':
    main()
