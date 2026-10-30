"""Test final gateway ZIP against an isolated final packaged kernel.

The Joomla-shaped origin here is a clearly labelled local mock. Actual Joomla
installation/browser checks run separately using release_joomla.ps1. This harness
never connects to or stops the working public gateway, Apache, database or tunnel.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import zipfile

import httpx


def stamp():
    return datetime.now(timezone.utc).isoformat()


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway',type=Path,required=True)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--python',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):
        raise ValueError('Use a new empty release test work directory; existing state is never removed')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    started=stamp();assertions=[];commands=[]
    package=work/'gateway';package.mkdir()
    with zipfile.ZipFile(args.gateway) as archive:
        for name in archive.namelist():
            if name.startswith('/') or '..' in name.replace('\\','/').split('/'):
                raise ValueError('Unsafe gateway member')
        archive.extractall(package)
    build_info=json.loads((package/'build-info.json').read_text())
    assert build_info['source_sha']==args.source_sha
    assert not (package/'gateway.json').exists()
    assert not (package/'cloudflare/quick-tunnel.json').exists()
    assert not (package/'scripts/Test-DragonApacheRecovery.ps1').exists()
    assertions.append('Final gateway archive embeds the release SHA and contains no live config/tunnel/outage helper')
    kernel=work/'kernel-state';kernel.mkdir()
    environment=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):
        environment.pop(key,None)
    logs=[];process=None;gateway_record=None;origin=None;origin_thread=None
    server_url=None;token=None
    client=httpx.Client(timeout=15,trust_env=False)
    result={'status':'running','started_at':started,'source_sha':args.source_sha,
            'gateway_sha256':hashlib.sha256(args.gateway.read_bytes()).hexdigest(),
            'assertions':assertions,'commands':commands,'joomla_origin_kind':'isolated mock; not actual Joomla install proof'}
    def ps(action):
        command=['pwsh','-NoLogo','-NoProfile','-NonInteractive','-File',str(package/'scripts'/action),'-StateDirectory',str(work/'gateway-state')]
        if action.startswith('Start'):
            command+=['-ConfigFile',str(package/'gateway.json'),'-Python',str(args.python.resolve()),'-Port','0']
        commands.append(command)
        completed=subprocess.run(command,capture_output=True,text=True,timeout=35)
        if completed.returncode:
            raise RuntimeError('Gateway helper failed: '+completed.stderr+completed.stdout)
        return json.loads(completed.stdout)
    def api(method,path,**kwargs):
        response=client.request(method,server_url+'/dragon/api/v1'+path,headers={'Authorization':'Bearer '+token},**kwargs)
        response.raise_for_status()
        return response.json()
    try:
        stdout=(work/'server.stdout.log').open('wb');stderr=(work/'server.stderr.log').open('wb');logs=[stdout,stderr]
        command=[str(args.server.resolve()),'--state',str(kernel),'--port','0','--init-bridge']
        commands.append(command)
        process=subprocess.Popen(command,cwd=work,env=environment,stdout=stdout,stderr=stderr)
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Isolated packaged server exited before ready')
            if (kernel/'endpoint.json').exists() and (kernel/'local-session.json').exists():
                server_url=json.loads((kernel/'endpoint.json').read_text())['url']
                token=json.loads((kernel/'local-session.json').read_text())['token']
                try:
                    if api('GET','/health/ready')['status']=='ready':
                        break
                except (httpx.HTTPError,ValueError):
                    pass
            time.sleep(.2)
        else:
            raise TimeoutError('Packaged kernel readiness timed out')
        assert (kernel/'joomla-bridge.json').is_file()
        assert client.get(server_url+'/dragon/api/v1/matches').status_code==401
        job=api('POST','/connections/openfootball/sync',json={'mode':'retained'})
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            progress=api('GET','/jobs/'+job['id'])
            if progress['status']=='succeeded':
                break
            assert progress['status'] not in ('failed','cancelled'),progress
            time.sleep(.2)
        else:
            raise TimeoutError('Retained import did not finish')
        source_count=api('GET','/matches?limit=1')['total']
        assert source_count>0
        assertions.append('Packaged kernel rejected anonymous direct reads and imported its documented retained dataset')

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*_):
                pass
            def do_GET(self):
                raw=b'<!doctype html><html><head><title>Isolated release origin</title></head><body><h1>Release mock origin</h1></body></html>'
                self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        origin=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        origin_thread=threading.Thread(target=origin.serve_forever,daemon=True);origin_thread.start()
        config={'joomla_origin':'http://127.0.0.1:'+str(origin.server_port),
                'api_endpoint_file':'../kernel-state/endpoint.json','bridge_secret_file':'../kernel-state/joomla-bridge.json','vps_public_ips':[]}
        # The relative paths are intentionally against the config's directory.
        config['api_endpoint_file']='../kernel-state/endpoint.json'
        config['bridge_secret_file']='../kernel-state/joomla-bridge.json'
        (package/'gateway.json').write_text(json.dumps(config),encoding='utf-8')
        gateway_record=ps('Start-PublicGateway.ps1');base=gateway_record['url']
        reused=ps('Start-PublicGateway.ps1')
        assert reused['reused'] and reused['pid']==gateway_record['pid']
        health=client.get(base+'/public-health').json()
        assert health['source_sha']==args.source_sha
        home=client.get(base+'/');assert home.status_code==200 and 'Browse DRAGONHYDRA matches' in home.text
        page=client.get(base+'/dragon/api/v1/matches?limit=1');page.raise_for_status();payload=page.json()
        assert payload['total']==source_count
        match=payload['items'][0]
        for path in ('/dragon/api/v1/teams/'+match['home']['id'],'/dragon/api/v1/competitions/'+match['competition_id']+'/standings','/sports/matches/'+match['id']):
            assert client.get(base+path).status_code==200,path
        assertions.append('Extracted portable helpers started/reused an isolated gateway; relative config references and reader bridge served actual match/team/standings')
        for path in ('/administrator/','/phpmyadmin/','/configuration.php','/dragon/api/v1/jobs','/dragon/api/v1/session','/dragon/api/v1/connections'):
            assert client.get(base+path).status_code==403,path
        assert client.post(base+'/dragon/api/v1/exports',json={}).status_code==403
        assertions.append('Final package denied administration, credentials, jobs, sessions, sources and state changes')
        origin.shutdown();origin.server_close();origin_thread.join(timeout=3);origin=None
        failed=client.get(base+'/');assert failed.status_code==503 and 'reconnecting' in failed.text
        assert client.get(base+'/dragon/api/v1/matches?limit=1').json()['total']==source_count
        assertions.append('Unavailable mock origin returned useful 503 while real packaged kernel browsing remained available')
        stopped=ps('Stop-PublicGateway.ps1');assert stopped['application_services_untouched']
        gateway_record=None
        restart=ps('Start-PublicGateway.ps1');gateway_record=restart
        assert client.get(restart['url']+'/dragon/api/v1/matches?limit=1').json()['total']==source_count
        assert (kernel/'core.sqlite3').is_file()
        assertions.append('Only test gateway stopped/restarted; test kernel data survived and no tunnel or live service was touched')
        result.update(status='passed',record_count=source_count,canonical_match_id=match['id'],finished_at=stamp())
    except Exception as error:
        result.update(status='failed',error=type(error).__name__+': '+str(error),finished_at=stamp())
        raise
    finally:
        if gateway_record or (work/'gateway-state/gateway-process.json').exists():
            try:
                ps('Stop-PublicGateway.ps1')
            except Exception as cleanup_error:
                result['cleanup_error']=type(cleanup_error).__name__+': '+str(cleanup_error)
                result['status']='failed'
        if origin:
            origin.shutdown();origin.server_close()
        if process and process.poll() is None:
            if server_url and token:
                try:api('POST','/system/shutdown',json={})
                except httpx.HTTPError:pass
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=10)
        for log in logs:log.close()
        client.close()
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'assertions':len(assertions),'source_sha':args.source_sha,'record_count':result.get('record_count')},indent=2))


if __name__=='__main__':
    run()
