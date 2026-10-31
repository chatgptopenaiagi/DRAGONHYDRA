"""Gated native optional-service acceptance; disable/restore in finally.

Uses the reviewed helper, installed /opt runtime, real R7 API jobs and retained
data. This is host-loopback integration, separate from the strict offline proof.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT/'packaging/linux-native/configure_local_ai.py'
HELPER_SHA = '372100a742398a11cbcfec1605a5497a5f67fb9b717100104d2c237faae3113b'
STATE = Path('/var/lib/dragonhydra-api')
MODEL_FILE = Path('/mnt/d/LocalAI/models/Qwen3-4B-Q4_K_M/Qwen3-4B-Q4_K_M.gguf')
API_URL = 'http://127.0.0.1:55971/dragon/api/v1'
PORT = 18765


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--execute-owned-service-test', action='store_true')
    args = parser.parse_args()
    if not args.execute_owned_service_test:
        parser.error('Integration-owner gate required; no host operation performed.')
    work = args.work.resolve()
    if (sys.platform != 'linux' or os.getuid() or work.exists()
            or work != ROOT/'build/linux/local-ai-20261031/configuration-r1/actual-r1'):
        raise SystemExit('Root, native Linux and fresh exact owned evidence directory required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'passed': False, 'started_at': datetime.now(timezone.utc).isoformat(), 'commands': [], 'checks': [],
              'scope': 'Actual optional systemd CPU service/installed runtime/R7 API; host namespace, no whole-host air-gap or desktop claim'}
    secrets_to_redact = []
    opener = build_opener(ProxyHandler({}))
    helper = controller = None
    apply_attempted = False
    held_env = None
    original = None
    def redact(value):
        value = str(value)
        for secret in secrets_to_redact: value = value.replace(secret, '[REDACTED]')
        return value
    def save(path, data): path.write_text(redact(json.dumps(data, indent=2))+'\n')
    def run(name, argv, timeout=180):
        begun = time.monotonic()
        child = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
        (work/(name+'.stdout.log')).write_text(redact(child.stdout))
        (work/(name+'.stderr.log')).write_text(redact(child.stderr))
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if child.returncode: raise RuntimeError(name+' returned '+str(child.returncode))
        return child.stdout
    def check(name, **fields):
        report['checks'].append({'name': name, 'passed': True, **fields})
        print(redact(json.dumps({'passed': name, **fields})), flush=True)
    def request(path, body=None, expected=200):
        token = json.loads((STATE/'local-session.json').read_text())['token']
        if token not in secrets_to_redact: secrets_to_redact.append(token)
        data = json.dumps(body).encode() if body is not None else None
        with opener.open(Request(API_URL+path, data=data, headers={'Authorization': 'Bearer '+token,'Content-Type':'application/json'}), timeout=5) as response:
            if response.status != expected: raise RuntimeError('Unexpected API status')
            return json.load(response)
    def snapshot():
        logical = {}
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%' ORDER BY name"):
                if not re.fullmatch('public_[a-z_]+', name): raise RuntimeError('Unsafe table identifier')
                columns = len(db.execute('PRAGMA table_info("'+name+'")').fetchall())
                rows = db.execute('SELECT * FROM "'+name+'" ORDER BY '+','.join(map(str,range(1,columns+1)))).fetchall()
                logical[name] = {'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}
        protected = {str(p): sha(p) if p.exists() else None for p in (
            Path('/usr/lib/systemd/system/dragonhydra-api.service'),Path('/etc/dragonhydra/api.env'),
            STATE/'local-session.json',STATE/'managed-port.json',STATE/'local-ai.json')}
        return {'public':logical,'protected':protected,'raw':{p.relative_to(STATE).as_posix():sha(p) for p in sorted((STATE/'raw').rglob('*')) if p.is_file()}}
    def ready():
        controller.api_guard()
        configuration = controller.host.api_configuration(wait=True)
        if request('/health/ready')['status'] != 'ready' or request('/matches?limit=1')['total'] != 760:
            raise RuntimeError('Core API/data readiness differs')
        return configuration
    def job(match_id, label):
        queued = request('/matches/'+match_id+'/local-explanations', {}, expected=202)
        deadline = time.monotonic()+65
        while time.monotonic() < deadline:
            result = request('/jobs/'+queued['id'])
            if result['status'] in ('succeeded','failed','cancelled','interrupted'):
                save(work/(label+'.json'),result)
                if result['status'] != 'succeeded': raise RuntimeError('Typed job did not succeed: '+label)
                return result
            time.sleep(.2)
        raise RuntimeError('Typed job deadline exceeded: '+label)
    def accepted(job_result, match_id):
        result, package = job_result['result'], job_result['payload']['package']
        sys.path.insert(0,'/opt/dragonhydra/api/site-packages')
        from dragonhydra import local_ai
        local_ai.validate_package(package)
        evidence = request('/evidence/'+package['evidence']['E1']['id'])
        raw_hash = evidence.get('source_hash') or evidence.get('raw_sha256')
        if (result['kind'] != 'local_llm' or result['mode'] != 'constrained_source_fact_selection'
                or not result['local_ai']['accepted'] or result['observations'][0] not in package['allowed_observations']
                or result['package_sha256'] != package['package_sha256'] or package['event']['id'] != match_id
                or result['evidence'][0]['id'] != package['evidence']['E1']['id']
                or raw_hash != package['evidence']['E1']['source_sha256'] or raw_hash not in original['raw'].values()):
            raise RuntimeError('Installed-prefix model result failed exact E1/package/source fact grounding')
        return {'job_id':job_result['id'],'kind':result['kind'],'mode':result['mode'],'observation':result['observations'][0],
                'evidence_id':result['evidence'][0]['id'],'raw_sha256':raw_hash,'package_sha256':package['package_sha256'],'runtime':result['runtime']}
    try:
        if sha(HELPER) != HELPER_SHA: raise RuntimeError('Reviewed/tested helper source changed')
        spec=importlib.util.spec_from_file_location('native_optional_ai_helper',HELPER)
        helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
        controller=helper.Controller()
        baseline=ready()
        if baseline['configured'] or baseline['endpoint'] or any(p.exists() for p in (helper.KEY,helper.ENV,helper.MARKER,helper.UNIT,helper.DROPIN)):
            raise RuntimeError('Refuse to replace existing optional AI configuration')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro',uri=True)) as db:
            if db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running','interrupted')").fetchone()[0]:
                raise RuntimeError('Other pending jobs exist; no controlled restart performed')
        original=snapshot();save(work/'before.json',original)
        match=request('/matches?status=finished&limit=1')['items'][0]
        # Test-phase budget isolation only. The normal helper never resets it.
        run('isolate-owned-api-test-budget',['systemctl','reset-failed',helper.API])
        apply_attempted=True
        run('enable-helper-once',['/usr/bin/python3','-B',HELPER,'enable','--model',MODEL_FILE,'--port',str(PORT)])
        key=helper.KEY.read_text().rstrip('\n');secrets_to_redact.append(key)
        key_hash=sha(helper.KEY);env_hash=sha(helper.ENV)
        controller.owner(strict=True);helper.Controller.model_guard(controller.host.state(helper.MODEL))
        configured=ready()
        if not configured['configured'] or request('/health/ready')['optional_ai']!='configured_not_tested':
            raise RuntimeError('API environment/passive-health contract differs')
        check('Helper enables actual DynamicUser model and optional R7 environment without an API dependency')
        try:
            opener.open(Request('http://127.0.0.1:'+str(PORT)+'/completion',data=b'{"prompt":"x","n_predict":1}',headers={'Content-Type':'application/json'}),timeout=3)
        except HTTPError as error:
            code=error.code;error.close()
            if code!=401:raise RuntimeError('Owned native model did not reject unauthenticated completion with401')
        else:
            raise RuntimeError('Owned native model accepted unauthenticated completion')
        check('Actual service credential loading enforces unauthenticated completion rejection')
        first=accepted(job(match['id'],'first-installed-prefix-job'),match['id']);report['first']=first
        check('Installed /opt runtime produces accepted exact E1 model fact via typed R7 API',job_id=first['job_id'])
        api_pid=controller.host.state(helper.API)['MainPID']
        controller.model_guard(controller.host.state(helper.MODEL))
        run('restart-only-owned-model',['systemctl','restart',helper.MODEL])
        controller.host.model_ready(PORT,key)
        if sha(helper.KEY)!=key_hash or sha(helper.ENV)!=env_hash or controller.host.state(helper.API)['MainPID']!=api_pid:
            raise RuntimeError('Model restart changed credentials or restarted the independent API')
        second=accepted(job(match['id'],'after-model-restart-job'),match['id']);report['after_restart']=second
        check('Model restart retains key/API process and accepted authenticated fact selection')
        controller.model_guard(controller.host.state(helper.MODEL))
        run('stop-only-owned-model',['systemctl','stop',helper.MODEL])
        ready()
        unavailable=job(match['id'],'stopped-model-fallback')['result']
        if unavailable['kind']!='deterministic' or unavailable['local_ai']['accepted'] or unavailable['local_ai']['code']!='AI_UNAVAILABLE':
            raise RuntimeError('Stopped model did not produce truthful bounded deterministic fallback')
        check('Core browsing remains ready with model stopped; unavailable inference is labelled deterministic')
        held_env=helper.ENV.read_bytes();helper.ENV.unlink()
        controller.api_guard();run('isolate-owned-missing-env-test-budget',['systemctl','reset-failed',helper.API])
        run('restart-owned-api-with-missing-optional-env',['systemctl','restart',helper.API])
        if ready()['configured'] or request('/health/ready')['optional_ai']!='not_configured':
            raise RuntimeError('Missing optional API environment blocked or misconfigured core startup')
        no_config=job(match['id'],'missing-env-fallback')['result']
        if no_config['kind']!='deterministic' or no_config['local_ai']['code']!='AI_NOT_CONFIGURED':
            raise RuntimeError('Missing optional environment did not use unconfigured deterministic fallback')
        helper.FileStore().atomic(helper.ENV,held_env,0o600);held_env=None
        check('Actual missing optional env-file API restart remains ready with760 matches and unconfigured fallback')
    except BaseException as error:
        report['error']={'type':type(error).__name__,'message':redact(error)}
        (work/'error.log').write_text(redact(traceback.format_exc()))
    finally:
        try:
            if helper is not None and held_env is not None:
                helper.FileStore().atomic(helper.ENV,held_env,0o600);held_env=None
            if apply_attempted and helper is not None:
                if helper.KEY.exists():
                    secret=helper.KEY.read_text().rstrip('\n')
                    if secret not in secrets_to_redact:secrets_to_redact.append(secret)
                owned_after_enable=helper.MARKER.exists()
                if owned_after_enable:
                    controller.owner();controller.api_guard();controller.model_guard(controller.host.state(helper.MODEL))
                    run('isolate-owned-disable-test-budget',['systemctl','reset-failed',helper.API])
                    run('disable-helper-finally',['/usr/bin/python3','-B',HELPER,'disable'])
                final_configuration=ready()
                final=snapshot();save(work/'after.json',final)
                model_state=controller.host.state(helper.MODEL)
                model_restored=(model_state.get('ActiveState')=='inactive' and
                    (model_state.get('UnitFileState')=='disabled' if owned_after_enable else not model_state.get('FragmentPath')))
                if (final!=original or final_configuration['configured'] or final_configuration['endpoint'] or helper.DROPIN.exists()
                        or not model_restored):
                    raise RuntimeError('Final disable did not restore original API/data and inactive disabled model')
                controller.owner(strict=True)
                if (owned_after_enable and not helper.KEY.exists()) or not helper.PROFILE.exists():raise RuntimeError('Disable removed retained key/profile')
                report['restored']={'url':'http://127.0.0.1:55971','records':760,'canonical_raw_pairing_base_config_equal':True,
                    'api_configuration':final_configuration,'model_state':model_state,'key_retained_root0600':bool(helper.KEY.exists()),
                    'profile_retained':True,'api_dropin_absent':True,'ownership_enabled':helper.MARKER.exists() and controller.owner()['enabled']}
                check('Disable/finally restores original unconfigured API760/data/pairing and retains protected key/profile')
        except BaseException as cleanup:
            report['cleanup_error']={'type':type(cleanup).__name__,'message':redact(cleanup)}
            (work/'cleanup-error.log').write_text(redact(traceback.format_exc()))
        report['passed']=bool(report.get('first') and report.get('after_restart') and report.get('restored') and not report.get('error') and not report.get('cleanup_error'))
        report['finished_at']=datetime.now(timezone.utc).isoformat();save(work/'verification.json',report)
    print(redact(json.dumps({k:report.get(k) for k in ('passed','first','after_restart','restored','error','cleanup_error')},indent=2)),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
