"""Guarded upgrade of the exact experimental R4 Debian API component to R5.

No apt, external download, other unit, source edit or networking change occurs.
Only the explicitly supplied vetted artifact is passed to native dpkg once.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sqlite3
import stat
import subprocess
import tarfile
import time
import traceback
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
PREFIX = Path('/opt/dragonhydra/api')
STATE = Path('/var/lib/dragonhydra-api')
ENV = Path('/etc/dragonhydra/api.env')
UNIT = 'dragonhydra-api.service'
VERSION4 = '0.4.0~alpha.1+dev20261031.9f3d6e5ab108-4'
VERSION5 = '0.4.0~alpha.1+dev20261031.9f3d6e5ab108-5'
BASE = '9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4'
EFFECTIVE = '6ceb72702f628c5be0a9440e5b12022e73e74bed95883be1c8d3ceabfc203b5a'
ARTIFACT = 'b2924f009fd9a19788ad998ba0540946b9badfad04b8cf0199b4e21f76d3e700'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    artifact, work = args.artifact.resolve(), args.work.resolve()
    if (platform.system() != 'Linux' or os.getuid() != 0 or work.exists()
            or not work.is_relative_to(ROOT/'build/linux/native-kernel-20261031')
            or not artifact.is_relative_to(ROOT/'dist/linux/native-kernel-20261031/r5')):
        raise SystemExit('Linux root, exact R5 artifact boundary and fresh project-local evidence required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'started_at': utc(), 'passed': False, 'scope': 'Actual guarded R4-to-R5 upgrade of exact experimental API component on Ubuntu26.04.1/WSL; no complete-workstation, desktop or clean-machine claim',
              'harness_sha256': digest(__file__), 'commands': [], 'checks': [], 'phases': []}
    token, base = '', ''
    opener = build_opener(ProxyHandler({}))

    def run(name, argv, expected=0, timeout=60):
        begun = time.monotonic()
        child = subprocess.run(list(map(str, argv)), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                               env={**os.environ, 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'DEBIAN_FRONTEND': 'noninteractive'})
        for suffix, value in [('stdout', child.stdout), ('stderr', child.stderr)]:
            (work/(name+'.'+suffix+'.log')).write_text(value.replace(token, '[REDACTED]') if token else value)
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if expected is not None and child.returncode != expected:
            raise RuntimeError(name+' exited '+str(child.returncode)+'; inspect saved native command logs')
        return child

    def archive_bytes(name, option):
        begun = time.monotonic()
        argv = ['dpkg-deb', option, str(artifact)]
        child = subprocess.run(argv, capture_output=True, timeout=30)
        report['commands'].append({'name': name, 'argv': argv, 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3), 'stdout_bytes': len(child.stdout)})
        if child.returncode:
            (work/(name+'.stderr.log')).write_bytes(child.stderr)
            raise RuntimeError(name+' native archive reader failed')
        return child.stdout

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name, **details}), flush=True)

    def owned_service(name):
        result = run(name, ['systemctl', 'show', UNIT, '-p', 'FragmentPath', '-p', 'ExecStart', '-p', 'DynamicUser',
                            '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID', '-p', 'NRestarts', '-p', 'Result'])
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if (props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes'
                or str(PREFIX/'bin/dragonhydra-server') not in props.get('ExecStart', '')
                or '--state '+str(STATE) not in props.get('ExecStart', '')):
            raise RuntimeError('Exact owned unit was not established')
        return props

    def request(path):
        with opener.open(Request(base+'/dragon/api/v1'+path, headers={'Authorization': 'Bearer '+token}), timeout=3) as response:
            if response.status != 200:
                raise RuntimeError('Unexpected API status')
            return json.load(response)

    def ready(phase, previous_pid=None, timeout=45):
        nonlocal token, base
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            props = owned_service(phase+'-service')
            pid = int(props.get('MainPID', '0'))
            if props.get('ActiveState') == 'active' and pid > 0 and pid != previous_pid:
                try:
                    endpoint = json.loads((STATE/'endpoint.json').read_text())
                    parsed = urlsplit(endpoint['url'])
                    if endpoint.get('pid') != pid:
                        time.sleep(.2)
                        continue
                    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
                            or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
                        raise RuntimeError('Owned endpoint URL shape mismatch')
                    token = json.loads((STATE/'local-session.json').read_text())['token']
                    base = endpoint['url'].rstrip('/')
                    if request('/health/ready')['status'] == 'ready':
                        value = {'phase': phase, 'pid': pid, 'url': base, 'nrestarts': int(props['NRestarts']), 'at': utc()}
                        report['phases'].append(value)
                        return value
                except (OSError, ValueError, URLError):
                    pass
            if props.get('ActiveState') == 'failed':
                raise RuntimeError('Exact unit failed during '+phase+'; '+props.get('Result', ''))
            time.sleep(.2)
        raise RuntimeError('Readiness deadline exceeded during '+phase)

    def snapshot():
        matches = request('/matches?limit=1')
        match = matches['items'][0]
        evidence = request('/evidence/'+match['evidence_id'])
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            counts = {name: db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in tables}
        return {'count': matches['total'], 'match_id': match['id'], 'evidence_id': match['evidence_id'],
                'match_version': match['version'], 'evidence_response_sha256': hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
                'pairing_sha256': hashlib.sha256(token.encode()).hexdigest(), 'public_sql_counts': counts}

    def env_semantics(payload):
        # Values remain only in memory, including any future configured keys.
        return [line.strip() for line in payload.splitlines() if line.strip() and not line.lstrip().startswith(b'#')]

    def audit_manifest(manifest, name):
        failures = []
        for entry in manifest['files']:
            relative = PurePosixPath(entry['path'])
            if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
                raise RuntimeError('Manifest path is unsafe')
            path = Path('/')/relative
            try:
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or digest(path) != entry['sha256'] or info.st_size != entry['bytes']
                        or stat.S_IMODE(info.st_mode) != int(entry['mode'], 8) or info.st_uid != entry['uid'] or info.st_gid != entry['gid']):
                    failures.append(entry['path'])
            except OSError:
                failures.append(entry['path'])
        (work/(name+'-payload-audit.json')).write_text(json.dumps({'files_checked': len(manifest['files']), 'failures': failures}, indent=2)+'\n')
        if failures:
            raise RuntimeError(name+' installed payload mismatch: '+str(failures[:8]))
        return len(manifest['files'])

    try:
        if artifact.stat().st_size != 2911412 or digest(artifact) != ARTIFACT:
            raise RuntimeError('Authorized exact R5 artifact size/hash mismatch')
        report['artifact'] = {'filename': artifact.name, 'bytes': artifact.stat().st_size, 'sha256': ARTIFACT}
        version = run('initial-package-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip()
        if version != 'install ok installed\n'+VERSION4:
            raise RuntimeError('Expected exact installed R4 package before one upgrade attempt')
        for path in (str(PREFIX/'BUILD-IDENTITY.json'), '/usr/lib/systemd/system/'+UNIT):
            owner = run('package-owner-'+Path(path).name, ['dpkg-query', '-S', path]).stdout.strip()
            if owner != 'dragonhydra-api: '+path:
                raise RuntimeError('Installed file ownership mismatch')
        initial_identity = json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        if initial_identity['debian_version'] != VERSION4 or initial_identity['source_content_sha256'] != BASE:
            raise RuntimeError('Installed R4 base identity mismatch')
        old_manifest = json.loads((ROOT/'dist/linux/native-kernel-20261031/PAYLOAD-MANIFEST.json').read_text())
        old_count = audit_manifest(old_manifest, 'r4')
        before_phase = ready('before-upgrade')
        report['before'] = snapshot()
        if report['before']['count'] != 760:
            raise RuntimeError('Expected preserved existing760 records; refusing to upgrade different state')
        original_env = ENV.read_bytes()
        env_info = ENV.lstat()
        if stat.S_IMODE(env_info.st_mode) != 0o600 or env_info.st_uid != 0 or env_info.st_gid != 0:
            raise RuntimeError('Expected existing root0600 configuration')
        if b'DRAGONHYDRA_PORT=0' not in env_semantics(original_env):
            raise RuntimeError('Expected original managed port0 semantics')
        report['configuration_before'] = {'sha256': digest(ENV), 'root0600': True}
        check('Exact installed R4 payload, owned native unit and retained state verified', files_checked=old_count, records=760,
              pid=before_phase['pid'], url=before_phase['url'])

        run('r5-control-extract', ['dpkg-deb', '--control', str(artifact), str(work/'control')])
        control = (work/'control/control').read_text()
        if 'Package: dragonhydra-api\n' not in control or 'Version: '+VERSION5+'\n' not in control or 'Architecture: amd64\n' not in control:
            raise RuntimeError('R5 control identity mismatch')
        run('r5-preinst-shell-syntax', ['sh', '-n', str(work/'control/preinst')])
        run('r5-postinst-shell-syntax', ['sh', '-n', str(work/'control/postinst')])
        run('r5-prerm-shell-syntax', ['sh', '-n', str(work/'control/prerm')])
        for required in ('Preserved the managed loopback port', "'systemctl', 'stop', UNIT", 'time.monotonic() + 75', "'upgrade'", 'MANAGED_ENDPOINT'):
            if required not in (work/'control/preinst').read_text():
                raise RuntimeError('Expected reviewed upgrade helper is absent from preinst: '+required)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes('native-control-archive', '--ctrl-tarfile')), mode='r:') as archive:
            for member in archive:
                path = PurePosixPath(member.name.removeprefix('./'))
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()) or member.uid or member.gid:
                    raise RuntimeError('Unexpected native control archive member')
                expected_mode = 0o755 if member.isdir() or path.name in ('preinst', 'postinst', 'prerm') else 0o644
                if member.mode != expected_mode:
                    raise RuntimeError('Unexpected native control mode: '+str(path))
        # Read Debian archive through its native reader, then validate all paths,
        # native archive modes and effective module identity before execution.
        packed = archive_bytes('native-payload-archive', '--fsys-tarfile')
        inventory = []
        with tarfile.open(fileobj=io.BytesIO(packed), mode='r:') as archive:
            names = set()
            for member in archive:
                relative = PurePosixPath(member.name.removeprefix('./'))
                if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative) or member.name in names:
                    raise RuntimeError('Unsafe or duplicate archive member')
                names.add(member.name)
                if member.uid != 0 or member.gid != 0 or not (member.isdir() or member.isfile()):
                    raise RuntimeError('Unexpected archive member type/ownership')
                if member.isdir() and member.mode != 0o755:
                    raise RuntimeError('Unexpected native directory mode')
                if member.isfile():
                    payload = archive.extractfile(member).read()
                    expected_mode = 0o600 if str(relative) == 'etc/dragonhydra/api.env' else 0o755 if str(relative) == 'opt/dragonhydra/api/bin/dragonhydra-server' else 0o644
                    if member.mode != expected_mode:
                        raise RuntimeError('Unexpected archive file mode: '+str(relative))
                    inventory.append({'path': str(relative), 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'mode': oct(member.mode), 'uid': 0, 'gid': 0})
                    if str(relative) == 'opt/dragonhydra/api/BUILD-IDENTITY.json':
                        identity = json.loads(payload)
                        if (identity['debian_version'] != VERSION5 or identity['source_content_sha256'] != EFFECTIVE
                                or identity['base_source_content_sha256'] != BASE):
                            raise RuntimeError('R5 effective/base content identity mismatch')
                        report['r5_identity'] = identity
            if not report.get('r5_identity'):
                raise RuntimeError('Missing R5 build identity')
        manifest5 = {'schema_version': 1, 'files': inventory}
        (work/'r5-archive-payload-manifest.json').write_text(json.dumps(manifest5, indent=2)+'\n')
        report['preinst_sha256'] = digest(work/'control/preinst')
        report['preflight_passed'] = True
        check('Exact R5 hash, native archive modes/control and preinst syntax verified', files_checked=len(inventory),
              base_source_content_sha256=BASE, effective_source_content_sha256=EFFECTIVE)
        # All guards passed. One native upgrade attempt only; no blind retries.
        print(json.dumps({'stage': 'native-dpkg-upgrade-start', 'at': utc()}), flush=True)
        run('native-dpkg-upgrade', ['dpkg', '--install', str(artifact)], timeout=150)
        version5 = run('final-package-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip()
        if version5 != 'install ok installed\n'+VERSION5:
            raise RuntimeError('Native dpkg did not finish configuring exact R5')
        after_phase = ready('after-upgrade', previous_pid=before_phase['pid'])
        if after_phase['url'] != before_phase['url']:
            raise RuntimeError('R4-to-R5 upgrade changed configured endpoint')
        report['after'] = snapshot()
        if report['after'] != report['before']:
            raise RuntimeError('Upgrade changed retained records/evidence/pairing')
        if env_semantics(ENV.read_bytes()) != env_semantics(original_env):
            raise RuntimeError('Upgrade changed active environment configuration semantics')
        report['configuration_after'] = {'sha256': digest(ENV), 'active_semantics_preserved': True,
                                         'bytes_unchanged': ENV.read_bytes() == original_env}
        installed_count = audit_manifest(manifest5, 'r5')
        cache = STATE/'managed-port.json'
        cache_info = cache.lstat()
        if (not stat.S_ISREG(cache_info.st_mode) or stat.S_IMODE(cache_info.st_mode) != 0o600
                or json.loads(cache.read_text())['port'] != urlsplit(after_phase['url']).port
                or (cache_info.st_uid, cache_info.st_gid) != (STATE.stat().st_uid, STATE.stat().st_gid)):
            raise RuntimeError('Managed cache mode/owner/endpoint mismatch')
        report['cache'] = {'mode': '0600', 'uid': cache_info.st_uid, 'gid': cache_info.st_gid, 'port': urlsplit(after_phase['url']).port}
        report['upgrade_passed'] = True
        check('Actual native R4-to-R5 upgrade retained same endpoint,760 records,evidence,pairing and config semantics',
              url=after_phase['url'], pid=after_phase['pid'], installed_files=installed_count)
        run('systemd-r5-acceptance', ['/usr/bin/python3', '-B', str(ROOT/'tests/installation/linux_systemd_package.py'),
                                    '--expected-version', VERSION5, '--work', str(work/'runtime')], timeout=150)
        acceptance = json.loads((work/'runtime/verification.json').read_text())
        report['acceptance'] = {'passed': acceptance['passed'], 'functional_checks_passed': acceptance['functional_checks_passed'],
                                'groups': len(acceptance['checks']), 'endpoint_history': acceptance.get('endpoint_history'),
                                'gaps': acceptance.get('gaps'), 'report': 'runtime/verification.json'}
        if not acceptance['passed'] or not acceptance['functional_checks_passed']:
            raise RuntimeError('R5 actual installed-unit acceptance failed; preserve exact evidence')
        report['passed'] = True
        check('Installed R5 lifecycle, API and fault recovery acceptance passed', groups=len(acceptance['checks']),
              endpoint_persistent=acceptance['endpoint_persistent'])
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raw = traceback.format_exc()
        (work/'error.log').write_text(raw.replace(token, '[REDACTED]') if token else raw)
    finally:
        try:
            report['final_service'] = owned_service('final-owned-service-observation')
            run('owned-unit-journal', ['journalctl', '-u', UNIT, '-b', '--no-pager', '-n', '220', '-o', 'short-iso'], expected=None)
        except BaseException as final_error:
            report['final_observation_error'] = str(final_error)
        report['finished_at'] = utc()
        (work/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ('passed', 'preflight_passed', 'upgrade_passed', 'error', 'acceptance', 'final_service')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
