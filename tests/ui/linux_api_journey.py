"""Bounded foreground WSL host and Windows-to-Linux HTTP acceptance probe.

No unit, WSL configuration, firewall, routing or permanent keepalive changes.
Session material stays in process memory and is never persisted or logged.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[2]
UNIT = 'dragonhydra-api.service'
STATE = Path('/var/lib/dragonhydra-api')
URL = 'http://127.0.0.1:55971'
VERSION = '0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
BASE = 'c77ddb3667f282407885e29a6d2a7b37c7b180d28672412771b5f616db4bb35a'
EFFECTIVE = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
WSL = r'C:\Windows\System32\wsl.exe'


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    temporary = path.with_name('.'+path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def holder(work, seconds):
    if platform.system() != 'Linux' or os.getuid() != 0 or not work.is_dir():
        raise SystemExit('Exact precreated evidence directory and Linux root required')
    begun = time.monotonic()
    report = {'started_at': utc(), 'helper_pid': os.getpid(), 'maximum_seconds': seconds,
              'unit_operations': 'Read-only inspection only; no start/stop/restart'}
    opener = build_opener(ProxyHandler({}))
    token = ''

    def snapshot():
        with opener.open(Request(URL+'/dragon/api/v1/matches?limit=1', headers={'Authorization': 'Bearer '+token}), timeout=3) as response:
            matches = json.load(response)
        match = matches['items'][0]
        return {'count': matches['total'], 'match_id': match['id'], 'evidence_id': match['evidence_id'],
                'version': match['version'], 'pairing_sha256': hashlib.sha256(token.encode()).hexdigest()}

    try:
        identity = json.loads(Path('/opt/dragonhydra/api/BUILD-IDENTITY.json').read_text())
        if (identity['debian_version'] != VERSION or identity['source_content_sha256'] != EFFECTIVE
                or identity['base_source_content_sha256'] != BASE):
            raise RuntimeError('Installed frozen R7 identity mismatch')
        deadline = min(begun+45, begun+seconds)
        while time.monotonic() < deadline:
            result = subprocess.run(['systemctl', 'show', UNIT, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState',
                                     '-p', 'UnitFileState', '-p', 'FragmentPath', '-p', 'DynamicUser', '-p', 'ExecStart'],
                                    capture_output=True, text=True, timeout=5, check=True)
            props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            if (props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes'
                    or '/opt/dragonhydra/api/bin/dragonhydra-server' not in props.get('ExecStart', '')
                    or '--state /var/lib/dragonhydra-api' not in props.get('ExecStart', '')):
                raise RuntimeError('Exact installed unit ownership guard failed')
            try:
                endpoint = json.loads((STATE/'endpoint.json').read_text())
                if (props['ActiveState'] == 'active' and props['UnitFileState'] == 'enabled'
                        and endpoint['pid'] == int(props['MainPID']) and endpoint['url'] == URL):
                    token = json.loads((STATE/'local-session.json').read_text())['token']
                    before = snapshot()
                    if before['count'] != 760:
                        raise RuntimeError('Existing retained records differ')
                    report.update(ready=True, before=before, observed_service=props, url=URL, ready_at=utc())
                    write(work/'holder-ready.json', report)
                    print('R7_FOREGROUND_HOLDER_READY', flush=True)
                    break
            except (OSError, ValueError, URLError):
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Read-only holder readiness deadline expired')
        while time.monotonic()-begun < seconds and not (work/'cancel-holder').exists():
            time.sleep(.2)
        report['cancelled_by_owned_file'] = (work/'cancel-holder').exists()
        report['after'] = snapshot()
        report['retained_state_equal'] = report['after'] == report['before']
        if not report['retained_state_equal']:
            raise RuntimeError('Probe changed retained matches/evidence/pairing')
        report['passed'] = True
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error).replace(token, '[REDACTED]') if token else str(error)}
        report['passed'] = False
    finally:
        report['seconds'] = round(time.monotonic()-begun, 3)
        report['finished_at'] = utc()
        write(work/'holder-finished.json', report)
    return 0 if report['passed'] else 1


def windows_probe(work, seconds):
    if platform.system() != 'Windows' or work.exists():
        raise SystemExit('Windows and a fresh evidence directory required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'started_at': utc(), 'passed': False, 'scope': 'Windows HTTP to real Linux API while one bounded foreground WSL command is active',
              'url': URL, 'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'maximum_holder_seconds': seconds, 'host_configuration_changed': False,
              'continuous_wsl_hosting_claim': False, 'browser_tested': False}
    holder_process = None
    token = ''
    streams = []
    def wsl_list():
        result = subprocess.run([WSL, '--list', '--verbose'], capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        text = result.stdout.decode('utf-16-le' if b'\x00' in result.stdout else 'utf-8', errors='replace')
        return {'exit_code': result.returncode, 'stdout': text.replace('\ufeff', '').strip(), 'at': utc()}
    try:
        report['wsl_before'] = wsl_list()
        relative = work.relative_to(ROOT).as_posix()
        command = [WSL, '--distribution', 'Ubuntu-26.04', '--user', 'root', '--cd', '/mnt/c/xampp/DRAGONHYDRA',
                   '--exec', '/usr/bin/python3', '-B', 'tests/ui/linux_api_journey.py', '--work', relative,
                   '--hold-linux', '--hold-seconds', str(seconds)]
        report['holder_command'] = command
        streams = [(work/'holder.stdout.log').open('w'), (work/'holder.stderr.log').open('w')]
        holder_process = subprocess.Popen(command, stdout=streams[0], stderr=streams[1], creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic()+65
        while not (work/'holder-ready.json').exists():
            if holder_process.poll() is not None:
                raise RuntimeError('Owned foreground holder exited before readiness; inspect its sanitized log')
            if time.monotonic() > deadline:
                raise RuntimeError('Owned foreground holder readiness receipt timed out')
            time.sleep(.2)
        report['linux_ready'] = json.loads((work/'holder-ready.json').read_text())
        report['wsl_during_holder'] = wsl_list()
        opener = build_opener(ProxyHandler({}))
        begun = time.monotonic()
        try:
            response = opener.open(URL+'/dragon/api/v1/health/live', timeout=5)
        except HTTPError as response_error:
            response = response_error
        except URLError as error:
            report['reachability_gap'] = {'code': 'WINDOWS_TO_WSL_LOCALHOST_UNREACHABLE_WHILE_FOREGROUND_ACTIVE',
                                          'message': str(error), 'seconds': round(time.monotonic()-begun, 3)}
            raise RuntimeError('Windows localhost remains unreachable while verified Linux API and foreground holder are active') from None
        with response:
            report['windows_unauthenticated_http'] = {'status': response.status, 'seconds': round(time.monotonic()-begun, 3)}
            response.read(4096)
            if response.status not in (200, 401):
                raise RuntimeError('Unexpected real API health status from Windows')
        # Capture root-readable token ONLY into this process's memory. Never
        # append this stdout/stderr or its value to any report or terminal log.
        code = "import json;from pathlib import Path;print(json.dumps({'token':json.loads(Path('/var/lib/dragonhydra-api/local-session.json').read_text())['token']}))"
        captured = subprocess.run([WSL, '--distribution', 'Ubuntu-26.04', '--user', 'root', '--exec', '/usr/bin/python3', '-B', '-c', code],
                                  capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        if captured.returncode:
            raise RuntimeError('Protected in-memory session retrieval failed; raw output was not logged')
        token = json.loads(captured.stdout)['token']
        for route in ('/health/ready', '/matches?limit=1'):
            with opener.open(Request(URL+'/dragon/api/v1'+route, headers={'Authorization': 'Bearer '+token}), timeout=5) as response:
                body = json.load(response)
                if route.startswith('/health') and body.get('status') != 'ready' or route.startswith('/matches') and body.get('total') != 760:
                    raise RuntimeError('Windows authenticated real API result differs')
                report.setdefault('windows_authenticated_http', []).append({'route': route, 'status': response.status,
                    'result': {'status': body.get('status')} if route.startswith('/health') else {'total': body['total'], 'match_id': body['items'][0]['id']}})
        report['passed'] = True
        print(json.dumps({'windows_to_linux_http': 'passed', 'url': URL, 'records': 760}), flush=True)
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error).replace(token, '[REDACTED]') if token else str(error)}
        trace = traceback.format_exc()
        (work/'error.log').write_text(trace.replace(token, '[REDACTED]') if token else trace)
    finally:
        if holder_process is not None:
            (work/'cancel-holder').write_text('Cancel only this bounded foreground test helper.\n')
            try:
                report['holder_exit_code'] = holder_process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                holder_process.terminate()
                report['holder_client_terminated_after_cancel_timeout'] = True
                report['holder_exit_code'] = holder_process.wait(timeout=10)
        for stream in streams:
            stream.close()
        if (work/'holder-finished.json').exists():
            report['holder_final'] = json.loads((work/'holder-finished.json').read_text())
        if report.get('holder_exit_code') != 0 or not report.get('holder_final', {}).get('passed'):
            report['passed'] = False
            report['holder_cleanup_failure'] = 'Owned bounded holder did not confirm retained state and a successful exit'
        report['wsl_after_helper_exit'] = wsl_list()
        report['finished_at'] = utc()
        write(work/'verification.json', report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'windows_unauthenticated_http', 'reachability_gap', 'error', 'holder_exit_code', 'browser_tested')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--hold-linux', action='store_true')
    parser.add_argument('--hold-seconds', type=int, default=180)
    args = parser.parse_args()
    work = args.work.resolve()
    if not work.is_relative_to(ROOT/'build/linux/native-kernel-20261031/browser-7') or not 30 <= args.hold_seconds <= 240:
        parser.error('Exact project browser-7 boundary and a30–240second foreground bound required')
    return holder(work, args.hold_seconds) if args.hold_linux else windows_probe(work, args.hold_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
