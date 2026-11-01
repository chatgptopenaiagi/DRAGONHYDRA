"""Verify a fresh installed server, bundled retained import and restart.

Uses only new caller-selected state and output directories. Provider requests,
model requests, service changes and existing databases are outside this helper.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

API = '/dragon/api/v1'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def utc():
    return datetime.now(timezone.utc).isoformat()


def windows_parent_pids():
    """Read process ancestry without changing or terminating any process."""
    import ctypes
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    library = ctypes.WinDLL('kernel32', use_last_error=True)
    library.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    library.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    library.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    library.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = library.CreateToolhelp32Snapshot(0x02, 0)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError('Owned process ancestry could not be inspected')
    entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
    parents = {}
    try:
        found = library.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            found = library.Process32NextW(handle, ctypes.byref(entry))
    finally:
        library.CloseHandle(handle)
    return parents


def owned_endpoint_pid(launcher_pid, endpoint_pid, *, windows=None, parents=None):
    """Windows venv redirectors may own a child; POSIX keeps exact PID checks."""
    if not isinstance(endpoint_pid, int) or isinstance(endpoint_pid, bool) or endpoint_pid <= 0:
        return False
    if endpoint_pid == launcher_pid:
        return True
    if not (os.name == 'nt' if windows is None else windows):
        return False
    parents = windows_parent_pids() if parents is None else parents
    visited = set()
    for _ in range(8):
        if endpoint_pid in visited:
            return False
        visited.add(endpoint_pid)
        endpoint_pid = parents.get(endpoint_pid, 0)
        if endpoint_pid == launcher_pid:
            return True
        if not endpoint_pid:
            return False
    return False


def run(args):
    python = str(args.python.absolute())  # Preserve venv symlinks.
    state, output = args.state.absolute(), args.output.absolute()
    require(not state.exists() and not output.exists(), 'Fresh state and output required')
    require(not state.is_relative_to(output) and not output.is_relative_to(state),
            'State and output must be separate')
    state.mkdir(parents=True, mode=0o700)
    output.mkdir(parents=True, mode=0o700)
    state, output = state.resolve(), output.resolve()
    report = {'schema_version': 1, 'started_at': utc(), 'passed': False,
              'scope': 'Fresh database initialization, bundled retained import and restart',
              'python': python, 'state': str(state), 'runtime_uid': os.getuid() if os.name == 'posix' else None,
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'provider_acquisitions_requested': False, 'model_inference_requested': False,
              'service_changes_requested': False, 'checks': [], 'processes': []}
    opener = build_opener(ProxyHandler({}))
    process, streams, token, base = None, [], '', ''

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})

    def request(path, body=None, *, expected=200, authenticate=True):
        headers = {'Authorization': 'Bearer '+token} if authenticate else {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(base+API+path, headers=headers,
                      data=canonical(body) if body is not None else None)
        try:
            response = opener.open(req, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            require(response.status == expected, f'{path}: HTTP {response.status}, expected {expected}')
            return json.loads(response.read())

    def start(index):
        nonlocal process, streams, token, base
        require(not (state/'endpoint.json').exists(), 'Unexpected endpoint before start')
        environment = dict(os.environ)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'DRAGONHYDRA_LOCAL_AI_URL', 'DRAGONHYDRA_LOCAL_AI_KEY'):
            environment.pop(name, None)
        if args.launcher:
            environment['DRAGONHYDRA_STATE'] = str(state)
            environment['DRAGONHYDRA_PORT'] = '0'
            command = [str(args.launcher.absolute())]
        else:
            command = [python, '-I', '-B', '-m', 'dragonhydra.server', '--state', str(state), '--port', '0']
        streams = [(output/f'server-{index}.stdout.log').open('w'),
                   (output/f'server-{index}.stderr.log').open('w')]
        process = subprocess.Popen(command, env=environment, stdout=streams[0], stderr=streams[1],
                                   **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        report['processes'].append({'pid': process.pid, 'command': command})
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            require(process.poll() is None, f'Server exited during startup: {process.returncode}')
            try:
                endpoint = json.loads((state/'endpoint.json').read_text())
                parsed = urlsplit(endpoint['url'])
                require(owned_endpoint_pid(process.pid, endpoint['pid']) and parsed.scheme == 'http'
                        and parsed.hostname == '127.0.0.1' and parsed.port
                        and not parsed.username and not parsed.password and not parsed.path
                        and not parsed.query and not parsed.fragment, 'Endpoint is not owned loopback')
                report['processes'][-1]['endpoint_pid'] = endpoint['pid']
                report['processes'][-1]['ownership_verification'] = ('exact launcher PID' if endpoint['pid'] == process.pid
                                                                   else 'Windows descendant of the live owned launcher')
                base = endpoint['url']
                token = json.loads((state/'local-session.json').read_text())['token']
                health = request('/health/ready')
                if health['status'] == 'ready':
                    if os.name == 'posix':
                        require(state.stat().st_mode & 0o777 == 0o700, 'State is not private')
                        require((state/'local-session.json').stat().st_mode & 0o777 == 0o600,
                                'Session file is not private')
                    check(f'startup_{index}', endpoint=endpoint, health=health)
                    return
            except (FileNotFoundError, json.JSONDecodeError, URLError):
                pass
            time.sleep(.1)
        raise TimeoutError('Server readiness deadline exceeded')

    def stop(index):
        nonlocal process, streams
        require(request('/system/shutdown', {})['status'] == 'stopping', 'Shutdown response differs')
        code = process.wait(timeout=45)
        report['processes'][-1]['exit_code'] = code
        require(code == 0 and not (state/'endpoint.json').exists(), 'Shutdown did not complete cleanly')
        process = None
        for stream in streams:
            stream.close()
        streams = []
        check(f'shutdown_{index}', exit_code=code)

    def import_retained():
        queued = request('/connections/openfootball/sync', {'mode': 'retained'}, expected=202)
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            item = request('/jobs/'+queued['id'])
            if item['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                require(item['status'] == 'succeeded', 'Retained import failed: '+str(item.get('error')))
                return item
            time.sleep(.1)
        raise TimeoutError('Retained import deadline exceeded')

    def records():
        pages = [request('/matches?limit=200&offset='+str(offset)) for offset in (0, 200, 400, 600)]
        require(all(page['total'] == 760 for page in pages), 'Retained count differs')
        rows = [item for page in pages for item in page['items']]
        require(len(rows) == len({item['id'] for item in rows}) == 760, 'Retained identities are incomplete')
        require(all(item['data_state'] in ('Historical', 'Scheduled') for item in rows), 'Synthetic records found')
        return rows

    try:
        probe = subprocess.run([python, '-I', '-B', '-c',
            "import json,sys,platform;from pathlib import Path;import dragonhydra;"
            "from dragonhydra.build_meta import info;root=Path(dragonhydra.__file__).parent/'resources/data/raw';"
            "print(json.dumps({'python':sys.version,'platform':platform.platform(),'module':dragonhydra.__file__,"
            "'build':info(),'bundled_sources':[p.name for p in root.glob('openfootball-*.json') if not p.name.endswith('.receipt.json')]}))"],
            capture_output=True, text=True, timeout=20)
        require(probe.returncode == 0, 'Installed resource probe failed')
        report['installed_environment'] = json.loads(probe.stdout)
        require(len(report['installed_environment']['bundled_sources']) == 2, 'Bundled source resources missing')
        start(1)
        require(request('/matches?limit=1')['total'] == 0, 'New state already contains records')
        require(request('/matches', expected=401, authenticate=False)['error']['code'] == 'AUTHENTICATION_REQUIRED',
                'Fresh state did not enforce authentication')
        require((state/'core.sqlite3').is_file(), 'Fresh database absent')
        check('fresh_database_initialized', records_before=0, authentication_http=401)
        imported = import_retained()
        require(imported['result']['record_count'] == imported['result']['inserted'] == 760,
                'Retained import counts differ')
        before = records()
        record_hash = hashlib.sha256(canonical(before)).hexdigest()
        selected = request('/matches/'+before[0]['id'])
        require(selected == before[0], 'Imported match cannot be retrieved')
        check('bundled_retained_import', records=760, job_id=imported['id'], result=imported['result'],
              records_sha256=record_hash, selected_match=selected)
        stop(1)
        start(2)
        require(records() == before, 'Retained records changed after restart')
        require(request('/jobs/'+imported['id'])['status'] == 'succeeded', 'Import job lost after restart')
        repeated = import_retained()
        require(repeated['result']['record_count'] == 760 and repeated['result']['inserted'] == 0,
                'Repeated retained import was not idempotent')
        require(records() == before, 'Repeated import changed retained records')
        with closing(sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
            require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SQLite integrity failure')
            require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'SQLite foreign-key failure')
        check('fresh_restart_persistence', records=760, records_sha256=record_hash,
              retained_job_id=imported['id'], repeated_inserted=0, sqlite_integrity='ok')
        stop(2)
        report['passed'] = True
    except BaseException as error:
        report['error'] = {'type': type(error).__name__,
                           'message': str(error).replace(token, '[REDACTED]') if token else str(error)}
    finally:
        if process is not None and process.poll() is None:
            try:
                request('/system/shutdown', {})
                process.wait(timeout=45)
                report['cleanup'] = {'method': 'authenticated_owned_shutdown', 'exit_code': process.returncode}
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                report['cleanup'] = {'method': 'owned_subprocess_terminated', 'exit_code': process.returncode}
        for stream in streams:
            stream.close()
        report['finished_at'] = utc()
        temporary = output/'verification.json.tmp'
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        os.replace(temporary, output/'verification.json')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']),
                      'error': report.get('error'), 'report': str(output/'verification.json')}))
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, type=Path)
    parser.add_argument('--launcher', type=Path, help='Installed run-server.sh; state/port passed through child environment')
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
