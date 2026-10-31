"""Gated real llama.cpp-to-installed-R7 API integration with memory-only keys.

The foreground harness owns one model process and one temporary /run drop-in.
It restores only its API unit configuration in finally. No provider requests,
API configuration writes, vault writes or whole-host air-gap claims occur.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/var/lib/dragonhydra-api')
UNIT = 'dragonhydra-api.service'
URL = 'http://127.0.0.1:55971'
VERSION = '0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
EFFECTIVE = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--runtime-manifest', type=Path, required=True)
    parser.add_argument('--runtime-manifest-sha256', required=True)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--server-sha256', required=True)
    parser.add_argument('--alias-manifest', type=Path, required=True)
    parser.add_argument('--alias-manifest-sha256', required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--model-sha256', required=True)
    parser.add_argument('--model-bytes', type=int, default=2497280256)
    parser.add_argument('--execute-integration', action='store_true')
    args = parser.parse_args()
    for value in (args.runtime_manifest_sha256, args.server_sha256, args.model_sha256, args.alias_manifest_sha256):
        if not re.fullmatch('[a-f0-9]{64}', value):
            parser.error('Supply each complete verified lowercase SHA256 from the runtime gate')
    if not args.execute_integration:
        parser.error('No host operation performed. Integration-owner runtime gate and --execute-integration required.')
    work = args.work.resolve()
    boundary = ROOT/'build/linux/local-ai-20261031/integration-r1'
    runtime, server, manifest, model = [p.resolve() for p in (args.runtime, args.server, args.runtime_manifest, args.model)]
    if (sys.platform != 'linux' or os.getuid() != 0 or work != boundary/'run' or work.exists()
            or runtime != ROOT/'runtime/linux-local-ai/llama-2280f0f-cpu-r1' or not server.is_relative_to(runtime)):
        raise SystemExit('Exact owned runtime/evidence paths, native Linux root and fresh work required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False, 'commands': [], 'checks': [],
              'scope': 'Actual DynamicUser R7 durable job to owned native CPU llama-server on host loopback; not a whole-host air gap or new sports analysis',
              'harness_sha256': digest(__file__), 'secret_persistence': 'Sealed root0600 memfd only; no key argv/envfile/token backup'}
    api_token = ''
    key = secrets.token_urlsafe(36)
    runner = None
    log_thread = None
    key_fd = env_fd = None
    dropin = None
    dropin_body = None
    dropin_created = False
    dropin_directory_created = False
    original = None
    baseline_dropins = None
    opener = build_opener(ProxyHandler({}))

    def redact(value):
        value = str(value).replace(key, '[REDACTED]')
        return value.replace(api_token, '[REDACTED]') if api_token else value

    def save(path, value):
        path.write_text(redact(json.dumps(value, indent=2))+'\n')

    def run(name, argv, expected=0, timeout=60):
        begun = time.monotonic()
        child = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
        (work/(name+'.stdout.log')).write_text(redact(child.stdout))
        (work/(name+'.stderr.log')).write_text(redact(child.stderr))
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if expected is not None and child.returncode != expected:
            raise RuntimeError(name+' exit'+str(child.returncode))
        return child.stdout

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print(redact(json.dumps({'passed': name, **details})), flush=True)

    def service(name):
        raw = run(name, ['systemctl', 'show', UNIT, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result',
                         '-p', 'FragmentPath', '-p', 'ExecStart', '-p', 'DynamicUser', '-p', 'DropInPaths'])
        props = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
        if (props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes'
                or '/opt/dragonhydra/api/bin/dragonhydra-server' not in props.get('ExecStart', '')
                or '--state /var/lib/dragonhydra-api' not in props.get('ExecStart', '')):
            raise RuntimeError('Exact owned API unit guard failed')
        return props

    def api(path, method='GET', body=None, expected=200):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(URL+'/dragon/api/v1'+path, data=data, method=method,
                          headers={'Authorization': 'Bearer '+api_token, 'Content-Type': 'application/json'})
        try:
            response = opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(2*1024*1024)
            if response.status != expected:
                raise RuntimeError('API '+method+' '+path+' returned HTTP'+str(response.status))
            return json.loads(raw)

    def ready(phase):
        nonlocal api_token
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            props = service(phase+'-service')
            try:
                endpoint = json.loads((STATE/'endpoint.json').read_text())
                if props['ActiveState'] == 'active' and endpoint['pid'] == int(props['MainPID']) and endpoint['url'] == URL:
                    api_token = json.loads((STATE/'local-session.json').read_text())['token']
                    health = api('/health/ready')
                    if health['status'] == 'ready' and api('/matches?limit=1')['total'] == 760:
                        return {'service': props, 'health': health}
            except (OSError, ValueError, URLError):
                pass
            if props.get('ActiveState') == 'failed':
                raise RuntimeError('Owned unit failed: '+props.get('Result', ''))
            time.sleep(.2)
        raise RuntimeError('Owned API readiness deadline exceeded')

    def snapshot():
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            logical = {}
            for table in sorted(tables):
                if not re.fullmatch('public_[a-z_]+', table):
                    raise RuntimeError('Unexpected public table name')
                cols = len(db.execute('PRAGMA table_info("'+table+'")').fetchall())
                rows = db.execute('SELECT * FROM "'+table+'" ORDER BY '+','.join(map(str, range(1, cols+1)))).fetchall()
                logical[table] = {'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}
        protected = {}
        for p in (Path('/etc/dragonhydra/api.env'), STATE/'local-session.json', STATE/'managed-port.json', STATE/'local-ai.json'):
            if p.exists():
                s = p.lstat()
                if not stat.S_ISREG(s.st_mode):
                    raise RuntimeError('Protected state is not regular')
                protected[str(p)] = {'sha256': digest(p), 'mode': oct(stat.S_IMODE(s.st_mode)), 'uid': s.st_uid, 'gid': s.st_gid}
            else:
                protected[str(p)] = {'absent': True}
        return {'public_tables': logical, 'protected': protected,
                'raw': [{'path': p.relative_to(STATE).as_posix(), 'sha256': digest(p)} for p in sorted((STATE/'raw').rglob('*')) if p.is_file()],
                'pairing_sha256': hashlib.sha256(api_token.encode()).hexdigest()}

    def sealed(data, name):
        fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.fchmod(fd, 0o600)
        os.write(fd, data)
        os.lseek(fd, 0, os.SEEK_SET)
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600 or fcntl.fcntl(fd, fcntl.F_GET_SEALS) != seals:
            os.close(fd)
            raise RuntimeError('Private sealed memfd verification failed')
        return fd

    def submit(match_id, label):
        queued = api('/matches/'+match_id+'/local-explanations', 'POST', {}, expected=202)
        deadline = time.monotonic()+70
        while time.monotonic() < deadline:
            current = api('/jobs/'+queued['id'])
            if current['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                save(work/(label+'.json'), current)
                if current['status'] != 'succeeded':
                    raise RuntimeError('Typed local-explanation job '+label+' ended '+current['status'])
                return current
            time.sleep(.2)
        raise RuntimeError('Bounded typed local-explanation job deadline expired')

    def stop_runner():
        if runner is not None and runner.poll() is None:
            runner.terminate()
            try:
                runner.wait(timeout=10)
            except subprocess.TimeoutExpired:
                runner.kill()
                runner.wait(timeout=5)
        if log_thread is not None:
            log_thread.join(timeout=5)

    try:
        if digest(manifest) != args.runtime_manifest_sha256 or digest(server) != args.server_sha256:
            raise RuntimeError('Exact gated runtime manifest/server hash mismatch')
        inventory = json.loads(manifest.read_text())
        if inventory.get('source', {}).get('commit') != '2280f0fd163b03d4331d49e08460f66502e35854' or len(inventory['runtime_files']) != 16:
            raise RuntimeError('Exact clean upstream runtime/source inventory differs')
        for entry in inventory['runtime_files']:
            rel = Path(entry['path'])
            if rel.is_absolute() or '..' in rel.parts:
                raise RuntimeError('Runtime inventory path unsafe')
            p = runtime/rel
            if not p.resolve().is_relative_to(runtime) or p.is_symlink() or digest(p) != entry['sha256'] or p.stat().st_size != entry['bytes']:
                raise RuntimeError('Runtime inventory bytes mismatch: '+str(rel))
        if digest(args.alias_manifest) != args.alias_manifest_sha256:
            raise RuntimeError('Exact approved runtime alias manifest hash mismatch')
        aliases = json.loads(args.alias_manifest.read_text())
        if (aliases['build_identity_sha256'] != args.runtime_manifest_sha256 or len(aliases['regular_files']) != 17
                or len(aliases['links']) != 12 or not aliases['passed']):
            raise RuntimeError('Runtime regular/link inventory counts or identity binding differ')
        for entry in aliases['regular_files']:
            rel = Path(entry['path'])
            p = runtime/rel
            if rel.is_absolute() or '..' in rel.parts or p.is_symlink() or not p.resolve().is_relative_to(runtime) or digest(p) != entry['sha256'] or p.stat().st_size != entry['bytes']:
                raise RuntimeError('Runtime companion regular file differs: '+str(rel))
        for entry in aliases['links']:
            rel = Path(entry['path'])
            p = runtime/rel
            if (rel.is_absolute() or '..' in rel.parts or not p.is_symlink() or os.readlink(p) != entry['target']
                    or not p.resolve().is_relative_to(runtime) or p.resolve().relative_to(runtime).as_posix() != entry['resolved_path']
                    or digest(p.resolve()) != entry['resolved_sha256'] or not entry['safe_contained_resolution']):
                raise RuntimeError('Runtime private SONAME link differs: '+str(rel))
        report['runtime_integrity'] = {'regular_files': 17, 'safe_relative_links': 12, 'manifest_sha256': args.runtime_manifest_sha256,
                                       'alias_manifest_sha256': args.alias_manifest_sha256, 'server_sha256': args.server_sha256}
        if model.stat().st_size != args.model_bytes or digest(model) != args.model_sha256:
            raise RuntimeError('Exact approved existing GGUF hash/size mismatch')
        with server.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                raise RuntimeError('Native server is not ELF')
        identity = json.loads(Path('/opt/dragonhydra/api/BUILD-IDENTITY.json').read_text())
        if identity['debian_version'] != VERSION or identity['source_content_sha256'] != EFFECTIVE:
            raise RuntimeError('Actual installed R7 identity differs')
        report['baseline_ready'] = ready('baseline')
        configuration = api('/local-model/configuration')
        if configuration['configured'] or configuration['endpoint'] or configuration['credential_source'] != 'none':
            raise RuntimeError('Preserve existing local AI settings; refusing to override configured state')
        if report['baseline_ready']['health']['optional_ai'] != 'not_configured':
            raise RuntimeError('Unexpected passive AI baseline')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            if db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running','interrupted')").fetchone()[0]:
                raise RuntimeError('Other pending jobs exist; refusing controlled API restart')
        original = snapshot()
        baseline_dropins = report['baseline_ready']['service']['DropInPaths']
        match = api('/matches?status=finished&limit=1')['items'][0]
        report['selected_match'] = {'id': match['id'], 'evidence_id': match['evidence_id']}
        help_text = run('native-server-help', [str(server), '--help'], timeout=20)
        for flag in ('--api-key-file', '--host', '--port', '--threads', '--ctx-size', '--parallel', '--n-predict'):
            if flag not in help_text:
                raise RuntimeError('Approved runtime lacks required flag '+flag)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        endpoint = 'http://127.0.0.1:'+str(port)
        key_fd = sealed((key+'\n').encode(), 'dragonhydra-test-model-key')
        env_fd = sealed(('DRAGONHYDRA_LOCAL_AI_URL='+endpoint+'\nDRAGONHYDRA_LOCAL_AI_KEY='+key+'\n').encode(), 'dragonhydra-test-unit-env')
        command = [str(server), '--model', str(model), '--host', '127.0.0.1', '--port', str(port), '--threads', '4',
                   '--threads-batch', '4', '--n-gpu-layers', '0', '--ctx-size', '2048', '--parallel', '1',
                   '--n-predict', '192', '--api-key-file', '/proc/self/fd/'+str(key_fd)]
        if '--offline' in help_text:
            command.append('--offline')
        report['runner_command'] = command
        runner = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, pass_fds=(key_fd,))
        def collect_log():
            with (work/'native-runner.log').open('w') as out:
                for line in runner.stdout:
                    out.write(redact(line))
                    out.flush()
        log_thread = threading.Thread(target=collect_log, daemon=True)
        log_thread.start()
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            if runner.poll() is not None:
                raise RuntimeError('Own model runner exited during load')
            try:
                with opener.open(Request(endpoint+'/health', headers={'Authorization': 'Bearer '+key}), timeout=2) as response:
                    if response.status == 200:
                        break
            except (URLError, OSError):
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Own model load deadline exceeded')
        try:
            opener.open(Request(endpoint+'/completion', data=b'{"prompt":"x","n_predict":1}', headers={'Content-Type':'application/json'}), timeout=3)
        except HTTPError as error:
            if error.code != 401:
                raise RuntimeError('Unauthenticated model request was not401')
            error.close()
        else:
            raise RuntimeError('Model runner unexpectedly accepted unauthenticated inference')
        check('Own native CPU runner loaded existing verified GGUF and enforces authentication', pid=runner.pid, port=port)
        directory = Path('/run/systemd/system')/(UNIT+'.d')
        if not directory.exists():
            directory.mkdir(mode=0o755)
            dropin_directory_created = True
        dropin = directory/('90-dragonhydra-memory-ai-'+secrets.token_hex(8)+'.conf')
        dropin_body = ('[Service]\nEnvironmentFile=/proc/'+str(os.getpid())+'/fd/'+str(env_fd)+'\n').encode()
        temporary = dropin.with_suffix('.tmp')
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(dropin_body)
                out.flush()
                os.fsync(out.fileno())
            # Publish the completed config without replacing an existing path.
            os.link(temporary, dropin)
            dropin_created = True
        finally:
            temporary.unlink(missing_ok=True)
        service('guard-before-temporary-dropin-reload')
        run('reload-own-temporary-unit-definition', ['systemctl', 'daemon-reload'])
        run('isolate-own-temporary-restart-budget', ['systemctl', 'reset-failed', UNIT])
        run('restart-only-own-api-with-memory-environment', ['systemctl', 'restart', UNIT])
        configured = ready('configured')
        current = api('/local-model/configuration')
        if (current != {'endpoint': endpoint, 'configured': True, 'endpoint_source': 'environment', 'credential_source': 'environment'}
                or configured['health']['optional_ai'] != 'configured_not_tested'
                or str(dropin) not in configured['service']['DropInPaths']):
            raise RuntimeError('PID1 did not supply expected memory-only environment to actual DynamicUser worker')
        process_status = Path('/proc/'+configured['service']['MainPID']+'/status').read_text()
        worker_uid = next(line.split()[2] for line in process_status.splitlines() if line.startswith('Uid:'))
        if not int(worker_uid):
            raise RuntimeError('Configured API worker unexpectedly runs as root')
        report['memory_configuration'] = {'worker_uid': int(worker_uid), 'root_env_memfd_mode': '0600',
                                           'key_and_env_memfds_sealed': True, 'dropin_path': str(dropin),
                                           'endpoint_source': 'environment', 'credential_source': 'environment'}
        check('Actual DynamicUser API reads sealed EnvironmentFile and reports passive configured_not_tested', worker_uid=int(worker_uid))
        job = submit(match['id'], 'accepted-model-job')
        result, package = job['result'], job['payload']['package']
        sys.path.insert(0, '/opt/dragonhydra/api/site-packages')
        from dragonhydra import local_ai
        local_ai.validate_package(package)
        evidence = api('/evidence/'+package['evidence']['E1']['id'])
        raw_sha = evidence.get('source_hash') or evidence.get('raw_sha256')
        if (result['kind'] != 'local_llm' or result['mode'] != 'constrained_source_fact_selection'
                or result['local_ai'] != {'requested': True, 'accepted': True}
                or result['package_sha256'] != package['package_sha256']
                or result['observations'][0] not in package['allowed_observations'] or len(result['observations']) != 1
                or package['event']['id'] != match['id'] or result['evidence'][0]['id'] != package['evidence']['E1']['id']
                or raw_sha != package['evidence']['E1']['source_sha256']
                or not any(entry['sha256'] == raw_sha for entry in original['raw'])
                or 'The model selected a supplied source fact; no new analysis or prediction was generated.' not in result['unknowns']):
            raise RuntimeError('Actual installed worker did not accept an exact grounded E1 model fact; no retry or validator weakening')
        if api('/health/ready')['optional_ai'] != 'configured_not_tested':
            raise RuntimeError('Passive configuration health was incorrectly promoted to runtime health')
        report['accepted'] = {'job_id': job['id'], 'kind': result['kind'], 'mode': result['mode'], 'match_id': match['id'],
                              'observation': result['observations'][0], 'evidence_id': result['evidence'][0]['id'],
                              'raw_sha256': raw_sha, 'package_sha256': package['package_sha256'], 'runtime': result['runtime']}
        check('Actual R7 durable worker accepted one exact supplied observation citing retained E1/raw/package hashes', job_id=job['id'])
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': redact(error)}
        (work/'error.log').write_text(redact(traceback.format_exc()))
    finally:
        try:
            stop_runner()
            if dropin_created:
                if dropin.read_bytes() != dropin_body:
                    raise RuntimeError('Owned temporary drop-in changed externally; preserve it for owner review')
                dropin.unlink()
                if dropin_directory_created:
                    try:
                        dropin.parent.rmdir()
                    except OSError:
                        pass
                service('guard-before-original-unit-restore')
                run('reload-original-unit-definition', ['systemctl', 'daemon-reload'])
                run('isolate-own-restoration-budget', ['systemctl', 'reset-failed', UNIT])
                run('restart-only-own-api-original-environment', ['systemctl', 'restart', UNIT])
            if original is not None:
                restored = ready('restored')
                current = api('/local-model/configuration')
                if (current != configuration or restored['health']['optional_ai'] != 'not_configured'
                        or restored['service']['DropInPaths'] != baseline_dropins or snapshot() != original):
                    raise RuntimeError('Original API settings/drop-ins/760records/evidence/pairing/cache/protections not restored')
                fallback = submit(match['id'], 'restored-deterministic-fallback')['result']
                if fallback['kind'] != 'deterministic' or fallback['local_ai']['accepted'] or fallback['local_ai']['code'] != 'AI_NOT_CONFIGURED':
                    raise RuntimeError('Restored deterministic fallback is not truthfully labelled')
                report['restored'] = {'url': URL, 'records': 760, 'settings': current, 'public_state_equal': True,
                                      'temporary_dropin_absent': dropin is None or not dropin.exists(), 'service': restored['service'],
                                      'deterministic_fallback_code': fallback['local_ai']['code']}
                check('Original unit settings and760records restored; unconfigured local action returns labelled deterministic fallback')
        except BaseException as cleanup:
            report['cleanup_error'] = {'type': type(cleanup).__name__, 'message': redact(cleanup)}
            (work/'cleanup-error.log').write_text(redact(traceback.format_exc()))
        for fd in (env_fd, key_fd):
            if fd is not None:
                os.close(fd)
        report['passed'] = bool(report.get('accepted') and report.get('restored') and not report.get('error') and not report.get('cleanup_error'))
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(work/'verification.json', report)
    print(redact(json.dumps({name: report.get(name) for name in ('passed', 'accepted', 'restored', 'error', 'cleanup_error')}, indent=2)), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
