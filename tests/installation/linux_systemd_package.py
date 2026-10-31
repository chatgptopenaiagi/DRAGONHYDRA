"""Verify only the explicitly installed DRAGONHYDRA API systemd component.

This changes its own experimental records and manages its exact package-owned
unit. It never installs packages, changes configuration, reboots WSL, or touches
other services. Endpoint changes are recorded as a product gap, not concealed.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import socket
import stat
import subprocess
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
UNIT = 'dragonhydra-api.service'
PREFIX = Path('/opt/dragonhydra/api')
STATE = Path('/var/lib/dragonhydra-api')
API = '/dragon/api/v1'
SOURCE = '9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--expected-version', default='0.4.0~alpha.1+dev20261031.9f3d6e5ab108-4')
    parser.add_argument('--expected-base-source', default=SOURCE)
    parser.add_argument('--expected-effective-source')
    args = parser.parse_args()
    for name, value in (('base', args.expected_base_source), ('effective', args.expected_effective_source)):
        if value is not None and not re.fullmatch('[a-f0-9]{64}', value):
            parser.error('Expected '+name+' source must be a complete lowercase SHA256')
    work = args.work.resolve()
    boundary = ROOT/'build/linux/native-kernel-20261031'
    if platform.system() != 'Linux' or os.getuid() != 0 or not work.is_relative_to(boundary) or work == boundary or work.exists():
        raise SystemExit('Run as Linux root with a fresh owned evidence directory beneath build/linux/native-kernel-20261031')
    work.mkdir(parents=True)
    report = {'schema_version': 1, 'started_at': utc_now(), 'passed': False, 'functional_checks_passed': False,
              'scope': 'Actual package installation and exact owned systemd unit on existing Ubuntu26.04.1/WSL; no clean-machine/full-workstation/desktop claim',
              'environment': {'platform': platform.platform(), 'python': platform.python_version(), 'uid': os.getuid()},
              'checks': [], 'commands': [], 'phases': [], 'gaps': [], 'network_acquisition': False}
    report['harness_sha256'] = digest(__file__)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    secret = ''
    base = ''
    opener = build_opener(ProxyHandler({}))

    def redact(value):
        return str(value).replace(secret, '[REDACTED]') if secret else str(value)

    def run(name, argv, expected=0, timeout=60):
        started = time.monotonic()
        result = subprocess.run(list(map(str, argv)), env={**os.environ, 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'},
                                capture_output=True, text=True, timeout=timeout)
        (work/(name+'.stdout.log')).write_text(redact(result.stdout))
        (work/(name+'.stderr.log')).write_text(redact(result.stderr))
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': result.returncode,
                                   'seconds': round(time.monotonic()-started, 3)})
        if expected is not None and result.returncode != expected:
            raise RuntimeError(name+' failed: '+redact(result.stderr)[-1000:])
        return result.stdout

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name, **details}), flush=True)

    def service(name):
        text = run(name, ['systemctl', 'show', UNIT, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState',
                          '-p', 'FragmentPath', '-p', 'ExecStart', '-p', 'DynamicUser', '-p', 'User', '-p', 'NRestarts'])
        props = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        if props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes':
            raise RuntimeError('Exact managed unit ownership was not established')
        command = props.get('ExecStart', '')
        if str(PREFIX/'bin/dragonhydra-server') not in command or '--state '+str(STATE) not in command:
            raise RuntimeError('The owned service command does not select the expected product and state')
        return props

    def request(path, method='GET', payload=None, expect=200, authenticate=True, timeout=15):
        headers = {'Content-Type': 'application/json'}
        if authenticate:
            headers['Authorization'] = 'Bearer '+secret
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            response = opener.open(Request(base+API+path, data=data, method=method, headers=headers), timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(4*1024*1024)
            if response.status != expect:
                raise RuntimeError(method+' '+path+' expected HTTP'+str(expect)+' received '+str(response.status))
            return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw

    def listeners(pid):
        inodes = set()
        for path in Path('/proc/'+str(pid)+'/fd').iterdir():
            try:
                value = os.readlink(path)
                if value.startswith('socket:['):
                    inodes.add(value[8:-1])
            except FileNotFoundError:
                pass
        result = []
        for line in Path('/proc/'+str(pid)+'/net/tcp').read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '0A' and fields[9] in inodes:
                address, port = fields[1].split(':')
                result.append({'address': socket.inet_ntoa(bytes.fromhex(address)[::-1]), 'port': int(port, 16)})
        return result

    def endpoint_history():
        urls = [item['url'] for item in report['phases']]
        stable = len(set(urls)) <= 1
        report['endpoint_persistent'] = stable
        report['endpoint_history'] = urls
        if not stable and not any(g['code'] == 'AUTOALLOCATED_ENDPOINT_CHANGED' for g in report['gaps']):
            report['gaps'].append({'code': 'AUTOALLOCATED_ENDPOINT_CHANGED', 'message': 'Default port0 selects a new endpoint after service restart; clients cannot retain one configured address.'})
        return stable

    def ready(phase, previous_pid=None, timeout=45):
        nonlocal secret, base
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            props = service(phase+'-service')
            pid = int(props.get('MainPID', '0'))
            if props.get('ActiveState') == 'active' and pid and pid != previous_pid:
                try:
                    endpoint = json.loads((STATE/'endpoint.json').read_text())
                    parsed = urlsplit(endpoint['url'])
                    if endpoint.get('pid') != pid or parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
                        time.sleep(.2)
                        continue
                    if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
                        raise RuntimeError('Unexpected service endpoint shape')
                    base = endpoint['url'].rstrip('/')
                    secret = json.loads((STATE/'local-session.json').read_text())['token']
                    health = request('/health/ready', timeout=3)
                    if health['status'] == 'ready':
                        sockets = listeners(pid)
                        if not sockets or any(s['address'] != '127.0.0.1' for s in sockets) or parsed.port not in [s['port'] for s in sockets]:
                            raise RuntimeError('The exact owned process does not have the expected private listener')
                        item = {'phase': phase, 'pid': pid, 'url': base, 'nrestarts': int(props.get('NRestarts', '0')), 'listeners': sockets}
                        report['phases'].append(item)
                        endpoint_history()
                        return item
                except (URLError, OSError, ValueError):
                    pass
            time.sleep(.2)
        raise RuntimeError('The exact owned unit did not become ready during '+phase)

    def job(path, payload):
        queued = request(path, 'POST', payload, expect=202)
        deadline = time.monotonic()+40
        while time.monotonic() < deadline:
            result = request('/jobs/'+queued['id'])
            if result['status'] == 'succeeded':
                return result['result']
            if result['status'] in ('failed', 'cancelled', 'interrupted'):
                raise RuntimeError('Owned test job failed: '+redact(json.dumps(result.get('error'))))
            time.sleep(.2)
        raise RuntimeError('Owned test job readiness deadline exceeded')

    def snapshot():
        page = request('/matches?limit=1')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            counts = {name: db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in tables}
        return {'count': page['total'], 'match_id': page['items'][0]['id'], 'evidence_id': page['items'][0]['version'],
                'pairing_sha256': hashlib.sha256(secret.encode()).hexdigest(), 'public_sql_counts': counts}

    def compare(before, phase):
        after = snapshot()
        if before != after:
            raise RuntimeError('Committed rows/evidence/pairing changed during '+phase)
        check('Committed records, evidence and pairing retained through '+phase, record_count=after['count'])
        return after

    try:
        identity = json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        version = run('dpkg-version', ['dpkg-query', '-W', '-f=${Version}', 'dragonhydra-api']).strip()
        if (version != args.expected_version or identity['debian_version'] != version
                or identity.get('base_source_content_sha256', identity['source_content_sha256']) != args.expected_base_source
                or (args.expected_effective_source is not None and identity['source_content_sha256'] != args.expected_effective_source)):
            raise RuntimeError('Installed package/source identity mismatch')
        if 'VERSION_ID="26.04"' not in Path('/etc/os-release').read_text():
            raise RuntimeError('This verifier targets the declared Ubuntu26.04 distribution')
        enabled = run('systemd-enabled', ['systemctl', 'is-enabled', UNIT]).strip()
        if enabled != 'enabled':
            raise RuntimeError('Installed systemd service is not enabled')
        report['installed_version'] = version
        report['base_source_content_sha256'] = args.expected_base_source
        report['source_content_sha256'] = identity['source_content_sha256']
        if identity.get('source_transforms'):
            module_info = json.loads((PREFIX/'site-packages/dragonhydra/build_info.json').read_text())
            transform = identity['source_transforms'][0]
            if (module_info['source_content_sha256'] != identity['source_content_sha256']
                    or module_info.get('base_source_content_sha256') != args.expected_base_source
                    or digest(PREFIX/'site-packages'/transform['target']) != transform['transformed_sha256']):
                raise RuntimeError('Effective patched source identity is inconsistent')
            report['source_transforms'] = identity['source_transforms']
        first = ready('initial')
        check('Actual installed package/source identity and enabled systemd readiness', pid=first['pid'], url=first['url'])

        permissions = {str(path): oct(stat.S_IMODE(path.stat().st_mode)) for path in (STATE, STATE/'local-session.json', Path('/etc/dragonhydra/api.env'))}
        if permissions != {str(STATE): '0o700', str(STATE/'local-session.json'): '0o600', '/etc/dragonhydra/api.env': '0o600'}:
            raise RuntimeError('Installed native filesystem protection mismatch')
        check('Native systemd state and credential permissions are enforced', permissions=permissions)
        if identity.get('source_transforms'):
            cache = STATE/'managed-port.json'
            if cache.is_symlink() or stat.S_IMODE(cache.stat().st_mode) != 0o600:
                raise RuntimeError('Persistent managed endpoint lacks native0600 protection')
            port = json.loads(cache.read_text())['port']
            if port != urlsplit(first['url']).port:
                raise RuntimeError('Saved managed port differs from the active service')
            check('Native protected managed endpoint matches the active listener', port=port, mode='0600')
        request('/matches?limit=1', authenticate=False, expect=401)
        before_count = request('/matches?limit=1')['total']
        if before_count not in (0, 760):
            raise RuntimeError('Unexpected records in this new experimental service; refusing to add fixtures')
        imported = job('/connections/openfootball/sync', {'mode': 'retained'})
        if imported['record_count'] != 760:
            raise RuntimeError('Retained fixture import did not produce 760 canonical records')
        check('Authenticated durable worker imports actual bundled public records', count=760, inserted=imported['inserted'])

        match = request('/matches?status=finished&limit=1')['items'][0]
        team = request('/teams/'+match['home']['id'])
        standing = request('/competitions/'+match['competition_id']+'/standings')
        if team['name'] != match['home']['name'] or len(standing['items']) != 20:
            raise RuntimeError('Same-match team/standings navigation mismatch')
        explanation = job('/matches/'+match['id']+'/explanations', {})
        evidence = request('/evidence/'+explanation['evidence'][0]['id'])
        if match['evidence_id'] != (evidence.get('evidence_id') or evidence.get('id')):
            raise RuntimeError('The cited source does not match the selected canonical event')
        check('Installed API match/team/20-team standings/cited explanation share one event', canonical_match_id=match['id'])

        exported = job('/exports', {'match_id': match['id'], 'format': 'xlsx'})
        workbook = request(exported['download_url'].removeprefix(API))
        with ZipFile(io.BytesIO(workbook)) as archive:
            assert '[Content_Types].xml' in archive.namelist()
            assert match['id'].encode() in archive.read('xl/worksheets/sheet1.xml')
            assert b'name="Metadata"' in archive.read('xl/workbook.xml')
        (work/'installed-match.xlsx').write_bytes(workbook)
        check('Actual installed-system Excel workbook downloaded and validated', bytes=len(workbook), sha256=hashlib.sha256(workbook).hexdigest())

        retained = snapshot()
        repeat = job('/connections/openfootball/sync', {'mode': 'retained'})
        if repeat['inserted'] != 0 or repeat['record_count'] != 760:
            raise RuntimeError('Repeated import duplicated retained canonical records')
        compare(retained, 'duplicate import')

        service('before-restart-ownership')
        # A preceding native upgrade has already started both the old and new
        # service. Give these intentional lifecycle scenarios a fresh test
        # budget; never alter the packaged restart interval or burst limit.
        run('isolate-owned-lifecycle-start-budget', ['systemctl', 'reset-failed', UNIT])
        run('restart-owned-unit', ['systemctl', 'restart', UNIT])
        second = ready('restart', previous_pid=first['pid'])
        compare(retained, 'managed restart')

        service('before-stop-ownership')
        run('stop-owned-unit', ['systemctl', 'stop', UNIT])
        inactive = service('stopped-service')
        if inactive['ActiveState'] != 'inactive' or int(inactive['MainPID']) != 0:
            raise RuntimeError('Owned unit did not stop cleanly')
        try:
            request('/health/live', authenticate=False, timeout=2)
        except (URLError, OSError):
            pass
        else:
            raise RuntimeError('Stopped owned API still answers at its former endpoint')
        check('Native stop leaves no managed API listener or main process')
        run('start-owned-unit', ['systemctl', 'start', UNIT])
        third = ready('start-after-stop', previous_pid=second['pid'])
        compare(retained, 'stop/start')

        service('before-failure-ownership')
        # Manual restart and stop/start above legitimately consume the same
        # configured StartLimitBurst budget. Isolate the ONE unexpected crash
        # scenario instead of treating our rapid fixture sequence as a daemon
        # recovery defect. The packaged burst/interval configuration is unchanged.
        run('isolate-owned-failure-start-budget', ['systemctl', 'reset-failed', UNIT])
        before_failure = service('fresh-failure-budget')
        pid = int(before_failure['MainPID'])
        cmdline = Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0', b' ').decode()
        if str(PREFIX/'bootstrap.py') not in cmdline or str(STATE) not in cmdline:
            raise RuntimeError('Refusing failure injection without the exact installed process/state identity')
        run('controlled-owned-main-failure', ['systemctl', 'kill', '--kill-whom=main', '--signal=SIGKILL', UNIT])
        fourth = ready('automatic-recovery', previous_pid=pid, timeout=45)
        if fourth['nrestarts'] <= int(before_failure['NRestarts']):
            raise RuntimeError('Expected bounded systemd automatic restart was not recorded')
        compare(retained, 'one controlled main-process failure')
        check('Systemd Restart=on-failure recovers exactly owned failed process', before_pid=pid, after_pid=fourth['pid'], restarts=fourth['nrestarts'])

        stable = endpoint_history()
        report['persistence'] = {'before': retained, 'after': snapshot()}
        report['functional_checks_passed'] = True
        report['passed'] = stable
        report['final_service'] = service('final-service')
    except Exception as exc:
        report['error'] = redact(type(exc).__name__+': '+str(exc))
        report['traceback'] = redact(traceback.format_exc())
    finally:
        try:
            current = service('cleanup-observe-owned-service')
            if current['ActiveState'] != 'active':
                run('restore-owned-unit-running', ['systemctl', 'start', UNIT])
                ready('restored-after-failure')
        except Exception as cleanup:
            report['cleanup_error'] = redact(str(cleanup))
        try:
            run('unit-journal', ['journalctl', '-u', UNIT, '--since', '15 minutes ago', '--no-pager', '-n', '160', '-o', 'short-iso'])
        except Exception as journal:
            report['journal_error'] = redact(str(journal))
        report['finished_at'] = utc_now()
        (work/'verification.json').write_text(redact(json.dumps(report, indent=2))+'\n')
        print(json.dumps({'passed': report['passed'], 'functional_checks_passed': report['functional_checks_passed'],
                          'groups': len(report['checks']), 'gaps': report['gaps'], 'error': report.get('error'),
                          'evidence': str(work/'verification.json')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
