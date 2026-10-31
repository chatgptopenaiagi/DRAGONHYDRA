"""Guarded upgrade/remove/reinstall of the verified experimental API component.

Never purges, deletes state, edits configuration or controls another unit.
Removal failures are measured before any reload/reinstall can conceal them.
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
import socket
import sqlite3
import stat
import subprocess
import tarfile
import time
import traceback
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/var/lib/dragonhydra-api')
PREFIX = Path('/opt/dragonhydra/api')
ENV = Path('/etc/dragonhydra/api.env')
UNIT = 'dragonhydra-api.service'
VERSION = '0.4.0~alpha.1+dev20261031.9f3d6e5ab108-5'
ARTIFACT = 'b2924f009fd9a19788ad998ba0540946b9badfad04b8cf0199b4e21f76d3e700'
EFFECTIVE = '6ceb72702f628c5be0a9440e5b12022e73e74bed95883be1c8d3ceabfc203b5a'
URL = 'http://127.0.0.1:55971'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--expected-version', default=VERSION)
    parser.add_argument('--sha256', default=ARTIFACT)
    parser.add_argument('--upgrade-from')
    parser.add_argument('--upgrade-work', type=Path)
    args = parser.parse_args()
    artifact, work = args.artifact.resolve(), args.work.resolve()
    version = args.expected_version
    if not re.fullmatch(r'0\.4\.0~alpha\.1\+dev20261031\.9f3d6e5ab108-[56]', version) or not re.fullmatch('[a-f0-9]{64}', args.sha256):
        raise SystemExit('Require an explicit verified R5/R6 identity and SHA256')
    revision = version.rsplit('-', 1)[1]
    boundary = ROOT/('build/linux/native-kernel-20261031/removal-'+revision)
    upgrade_work = args.upgrade_work.resolve() if args.upgrade_work else None
    if (platform.system() != 'Linux' or os.getuid() != 0 or work.exists() or not work.is_relative_to(boundary)
            or not artifact.is_relative_to(ROOT/('dist/linux/native-kernel-20261031/r'+revision))
            or (args.upgrade_from is not None and (args.upgrade_from != VERSION or version == VERSION or upgrade_work is None))
            or (upgrade_work is not None and (upgrade_work != ROOT/('build/linux/native-kernel-20261031/system-install-'+revision) or upgrade_work.exists()))):
        raise SystemExit('Require native Linux root, fresh owned evidence and exact authorized package boundaries')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Exact experimental API component upgrade/remove/reinstall on existing Ubuntu26.04/WSL, not purge/full-workstation/clean-machine',
              'expected_version': version, 'expected_artifact_sha256': args.sha256,
              'harness_sha256': sha(__file__), 'commands': [], 'checks': [], 'removal_failures': [],
              'manual_daemon_reload_before_measurement': False}
    token = ''
    remove_attempted = False
    opener = build_opener(ProxyHandler({}))
    if upgrade_work:
        upgrade_work.mkdir()
        (upgrade_work/'harness-source.py').write_bytes(Path(__file__).read_bytes())

    def run(name, argv, expected=0, timeout=60):
        begun = time.monotonic()
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout,
                                env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
        for stream, value in [('stdout', result.stdout), ('stderr', result.stderr)]:
            (work/(name+'.'+stream+'.log')).write_text(value.replace(token, '[REDACTED]') if token else value)
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': result.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if expected is not None and result.returncode != expected:
            raise RuntimeError(name+' exit'+str(result.returncode))
        return result

    def check(name, passed=True, **details):
        report['checks'].append({'name': name, 'passed': passed, **details})
        if not passed:
            report['removal_failures'].append({'code': name, **details})
        print(json.dumps({'check': name, 'passed': passed, **details}), flush=True)

    def service(name, guard=True):
        result = run(name, ['systemctl', 'show', UNIT, '-p', 'FragmentPath', '-p', 'LoadState', '-p', 'UnitFileState',
                            '-p', 'ExecStart', '-p', 'DynamicUser', '-p', 'ActiveState', '-p', 'SubState',
                            '-p', 'MainPID', '-p', 'Result', '-p', 'NRestarts'], expected=None)
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if guard and (props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes'
                      or str(PREFIX/'bin/dragonhydra-server') not in props.get('ExecStart', '')
                      or '--state '+str(STATE) not in props.get('ExecStart', '')):
            raise RuntimeError('Exact product-owned unit identity mismatch')
        return props

    def request(path):
        with opener.open(Request(URL+'/dragon/api/v1'+path, headers={'Authorization': 'Bearer '+token}), timeout=3) as response:
            return json.load(response)

    def ready(phase):
        nonlocal token
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            props = service(phase+'-service')
            try:
                endpoint = json.loads((STATE/'endpoint.json').read_text())
                if props.get('ActiveState') == 'active' and endpoint['pid'] == int(props['MainPID']) and endpoint['url'] == URL:
                    token = json.loads((STATE/'local-session.json').read_text())['token']
                    if request('/health/ready')['status'] == 'ready':
                        return {'service': props, 'url': URL, 'count': request('/matches?limit=1')['total']}
            except (OSError, ValueError, URLError):
                pass
            if props.get('ActiveState') == 'failed':
                raise RuntimeError('Owned unit failed with '+props.get('Result', ''))
            time.sleep(.2)
        raise RuntimeError('Exact retained endpoint not ready during '+phase)

    def snapshot():
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            logical = {}
            for table in sorted(tables):
                if not re.fullmatch(r'public_[a-z_]+', table):
                    raise RuntimeError('Unexpected public table identifier')
                columns = len(db.execute('PRAGMA table_info("'+table+'")').fetchall())
                rows = db.execute('SELECT * FROM "'+table+'" ORDER BY '+','.join(map(str, range(1, columns+1)))).fetchall()
                payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b: {'bytes_hex': b.hex()}).encode()
                logical[table] = {'rows': len(rows), 'sha256': hashlib.sha256(payload).hexdigest()}
        raw = [{'path': p.relative_to(STATE).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted((STATE/'raw').rglob('*')) if p.is_file()]
        secret = json.loads((STATE/'local-session.json').read_text())['token']
        paths = (ENV, STATE/'local-session.json', STATE/'managed-port.json')
        protections = {str(p): {'mode': oct(stat.S_IMODE(p.stat().st_mode)), 'uid': p.stat().st_uid, 'gid': p.stat().st_gid} for p in paths}
        return {'public_tables': logical, 'raw_evidence': raw,
                'pairing_token_sha256': hashlib.sha256(secret.encode()).hexdigest(),
                'pairing_file_sha256': sha(STATE/'local-session.json'), 'cache_sha256': sha(STATE/'managed-port.json'),
                'configuration_sha256': sha(ENV), 'protections': protections}

    def metadata(path):
        path = Path(path)
        if path.is_symlink():
            return {'path': str(path), 'kind': 'symlink', 'target': os.readlink(path), 'target_exists': path.exists()}
        if path.is_file():
            return {'path': str(path), 'kind': 'regular', 'bytes': path.stat().st_size, 'sha256': sha(path)}
        return {'path': str(path), 'kind': 'absent'}

    def audit_installed(manifest, name):
        for entry in manifest['files']:
            path = Path('/')/entry['path']
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or sha(path) != entry['sha256'] or info.st_size != entry['bytes']
                    or stat.S_IMODE(info.st_mode) != int(entry['mode'], 8) or info.st_uid != 0 or info.st_gid != 0):
                raise RuntimeError(name+' static payload mismatch: '+entry['path'])

    def native_archive(option):
        argv = ['dpkg-deb', option, str(artifact)]
        begun = time.monotonic()
        child = subprocess.run(argv, capture_output=True, timeout=30)
        report['commands'].append({'name': option, 'argv': argv, 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3), 'stdout_bytes': len(child.stdout)})
        if child.returncode:
            raise RuntimeError('Native archive reader failed: '+option)
        return child.stdout

    def candidate_preflight():
        run('candidate-control-extract', ['dpkg-deb', '--control', str(artifact), str(work/'control')])
        control = (work/'control/control').read_text()
        if ('Package: dragonhydra-api\n' not in control or 'Version: '+version+'\n' not in control
                or 'Architecture: amd64\n' not in control):
            raise RuntimeError('Candidate control identity mismatch')
        scripts = ['preinst', 'postinst', 'prerm']+(['postrm'] if revision == '6' else [])
        for script in scripts:
            run(script+'-shell-syntax', ['sh', '-n', str(work/'control'/script)])
        inventory = []
        identity = None
        with tarfile.open(fileobj=io.BytesIO(native_archive('--fsys-tarfile')), mode='r:') as archive:
            names = set()
            for member in archive:
                path = PurePosixPath(member.name.removeprefix('./'))
                if path.is_absolute() or '..' in path.parts or '\\' in str(path) or str(path) in names or not (member.isdir() or member.isfile()) or member.uid or member.gid:
                    raise RuntimeError('Unsafe native payload member')
                names.add(str(path))
                expected_mode = (0o755 if member.isdir() or str(path) == 'opt/dragonhydra/api/bin/dragonhydra-server'
                                 else 0o600 if str(path) == 'etc/dragonhydra/api.env' else 0o644)
                if member.mode != expected_mode:
                    raise RuntimeError('Unexpected native mode: '+str(path))
                if member.isfile():
                    payload = archive.extractfile(member).read()
                    inventory.append({'path': str(path), 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                                      'mode': oct(member.mode), 'uid': 0, 'gid': 0})
                    if str(path) == 'opt/dragonhydra/api/BUILD-IDENTITY.json':
                        identity = json.loads(payload)
        with tarfile.open(fileobj=io.BytesIO(native_archive('--ctrl-tarfile')), mode='r:') as archive:
            for member in archive:
                path = PurePosixPath(member.name.removeprefix('./'))
                if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()) or member.uid or member.gid:
                    raise RuntimeError('Unsafe native control member')
                if member.mode != (0o755 if member.isdir() or path.name in scripts else 0o644):
                    raise RuntimeError('Unexpected native control mode')
        if not identity or identity['debian_version'] != version or identity['source_content_sha256'] != EFFECTIVE:
            raise RuntimeError('Candidate effective source identity mismatch')
        if revision == '6':
            inputs = identity['packaging_inputs']
            if len(inputs) != 11:
                raise RuntimeError('R6 must record all eleven packaging inputs')
            for entry in inputs:
                path = PurePosixPath(entry['path'])
                if path.name != str(path) or sha(ROOT/'packaging/linux-native'/path) != entry['sha256']:
                    raise RuntimeError('Reviewed packaging input mismatch: '+str(path))
            source_dir = ROOT/'packaging/linux-native'
            if (work/'control/postrm').read_bytes() != (source_dir/'postrm').read_bytes():
                raise RuntimeError('Native postrm differs from reviewed narrow source')
            postrm = (work/'control/postrm').read_text()
            if ('deb-systemd-helper purge dragonhydra-api.service >/dev/null' not in postrm
                    or 'systemctl daemon-reload' not in postrm or 'remove|purge)' not in postrm or 'DPKG_ROOT' not in postrm):
                raise RuntimeError('Expected guarded unit-only cleanup is absent')
            executable_lines = [line.strip() for line in postrm.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            if any(line.startswith(('rm ', 'dpkg ', 'apt ', 'systemctl stop ', 'systemctl disable ')) for line in executable_lines):
                raise RuntimeError('Unexpected postrm command outside reviewed unit-only bookkeeping')
            expected_preinst = (source_dir/'preinst.in').read_text().replace('@@MANAGED_ENDPOINT@@', (source_dir/'managed_endpoint.py').read_text()).encode()
            if (work/'control/preinst').read_bytes() != expected_preinst:
                raise RuntimeError('Preinst does not embed the reviewed endpoint helper')
        result = {'schema_version': 1, 'files': inventory}
        (work/'candidate-payload-manifest.json').write_text(json.dumps(result, indent=2)+'\n')
        report['candidate'] = {'filename': artifact.name, 'bytes': artifact.stat().st_size, 'sha256': args.sha256,
                               'files': len(inventory), 'packaging_inputs': len(identity['packaging_inputs']),
                               'shell_scripts_checked': scripts, 'effective_source_content_sha256': EFFECTIVE}
        return result

    try:
        if sha(artifact) != args.sha256:
            raise RuntimeError('Exact unchanged authorized archive hash mismatch')
        candidate = candidate_preflight()
        initial_version = args.upgrade_from or version
        if run('initial-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+initial_version:
            raise RuntimeError('Require exact expected initial package before mutation')
        identity = json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        if identity['debian_version'] != initial_version or identity['source_content_sha256'] != EFFECTIVE:
            raise RuntimeError('Installed effective source identity mismatch')
        for path in (str(PREFIX/'BUILD-IDENTITY.json'), '/usr/lib/systemd/system/'+UNIT):
            if run('owner-'+Path(path).name, ['dpkg-query', '-S', path]).stdout.strip() != 'dragonhydra-api: '+path:
                raise RuntimeError('Native package ownership mismatch')
        manifest = (json.loads((ROOT/'build/linux/native-kernel-20261031/system-install-5/upgrade/r5-archive-payload-manifest.json').read_text())
                    if args.upgrade_from else candidate)
        audit_installed(manifest, initial_version)
        report['before_ready'] = ready('before-removal')
        if report['before_ready']['count'] != 760:
            raise RuntimeError('Expected existing760 records')
        report['before'] = snapshot()
        # The parent wrapper restricts this new directory's Windows ACL before
        # WSL writes. No pairing/token/config files are copied into the backup.
        private = boundary/'private-evidence'
        if not private.is_dir() or not (private/'ACL-RESTRICTED.json').is_file():
            raise RuntimeError('Private project backup ACL was not established')
        backup = private/'core-before-removal.sqlite3'
        if backup.exists():
            raise RuntimeError('Preserve existing private database snapshot')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Consistent backup failed integrity check')
        report['private_sqlite_backup'] = {'path': 'private-evidence/core-before-removal.sqlite3', 'sha256': sha(backup), 'consistent_sqlite_backup': True,
                                           'token_configuration_files_not_copied': True, 'protection': 'Windows ACL established by wrapper; no DrvFS chmod claim'}
        check('Guarded native payload and consistent private760-record backup', files_checked=len(manifest['files']))
        if args.upgrade_from:
            report['before_upgrade'] = report['before']
            print(json.dumps({'stage': 'guarded-native-upgrade-once', 'from': initial_version, 'to': version}), flush=True)
            run('native-upgrade-once', ['dpkg', '--install', str(artifact)], timeout=120)
            upgraded = service('after-upgrade-observation')
            if upgraded.get('Result') == 'start-limit-hit':
                run('isolate-only-owned-upgrade-start-budget', ['systemctl', 'reset-failed', UNIT])
                run('start-only-owned-upgraded-unit', ['systemctl', 'start', UNIT])
            report['after_upgrade_ready'] = ready('after-upgrade')
            report['after_upgrade'] = snapshot()
            if report['after_upgrade'] != report['before_upgrade']:
                raise RuntimeError('Upgrade changed retained state')
            if run('upgraded-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+version:
                raise RuntimeError('Exact upgrade did not configure')
            audit_installed(candidate, version)
            manifest = candidate
            report['upgrade_passed'] = True
            (upgrade_work/'verification.json').write_text(json.dumps({'passed': True, 'before': report['before_upgrade'],
                'after': report['after_upgrade'], 'ready': report['after_upgrade_ready'], 'candidate': report['candidate'],
                'native_command': next(c for c in report['commands'] if c['name'] == 'native-upgrade-once'),
                'full_evidence': '../removal-'+revision+'/run/verification.json'}, indent=2)+'\n')
            check('EXACT_UPGRADE_READY_SAME_ENDPOINT760_AND_RETAINED_HASHES', url=URL, version=version)
        remove_attempted = True
        run('native-remove-once', ['dpkg', '--remove', 'dragonhydra-api'], timeout=90)
        report['after_removal_service'] = removed = service('after-removal-before-any-reload', guard=False)
        report['after_removal_package'] = run('removed-package-status', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api'], expected=None).stdout.strip()
        enabled = run('after-removal-enabled', ['systemctl', 'is-enabled', UNIT], expected=None)
        report['after_removal_enabled'] = {'exit_code': enabled.returncode, 'stdout': enabled.stdout.strip()}
        check('OWNED_UNIT_STOPPED_AFTER_REMOVE', removed.get('ActiveState') == 'inactive' and int(removed.get('MainPID', '0')) == 0)
        check('OWNED_UNIT_NOT_LOADABLE_AFTER_REMOVE', removed.get('LoadState') == 'not-found', actual_load_state=removed.get('LoadState'), actual_fragment=removed.get('FragmentPath'))
        check('OWNED_UNIT_NOT_ENABLED_AFTER_REMOVE', enabled.returncode != 0 and enabled.stdout.strip() not in ('enabled', 'enabled-runtime'))
        try:
            with socket.create_connection(('127.0.0.1', 55971), timeout=2):
                live = True
        except OSError:
            live = False
        check('NO_RETAINED_API_LISTENER_AFTER_REMOVE', not live)
        remaining = [entry['path'] for entry in manifest['files'] if entry['path'] != 'etc/dragonhydra/api.env' and (Path('/')/entry['path']).exists()]
        check('PACKAGED_NON_CONFIG_FILES_REMOVED', not remaining, remaining=remaining)
        states = [metadata(path) for path in (
            '/etc/systemd/system/multi-user.target.wants/'+UNIT,
            '/etc/systemd/system/'+UNIT,
            '/var/lib/systemd/deb-systemd-helper-enabled/'+UNIT+'.dsh-also',
            '/var/lib/systemd/deb-systemd-helper-enabled/multi-user.target.wants/'+UNIT,
            '/var/lib/systemd/deb-systemd-helper-masked/'+UNIT)]
        report['after_removal_enablement_and_helper_state'] = states
        dangling = [entry for entry in states[:2] if entry['kind'] == 'symlink' and not entry['target_exists']]
        check('NO_DANGLING_SYSTEMD_ENABLEMENT_SYMLINK', not dangling, dangling=dangling)
        after = snapshot()
        report['while_removed'] = after
        check('ALL_CANONICAL_ROWS_EVIDENCE_PAIRING_CACHE_CONFIG_RETAINED_WHILE_REMOVED', after == report['before'])
        report['removal_checks_completed'] = True
    except BaseException as failure:
        report['error'] = {'type': type(failure).__name__, 'message': str(failure)}
        (work/'error.log').write_text(traceback.format_exc().replace(token, '[REDACTED]') if token else traceback.format_exc())
    finally:
        if remove_attempted:
            try:
                # Required restoration occurs once even if removal assertions
                # exposed a defect. Never purge/retry dpkg or reload manually.
                print(json.dumps({'stage': 'restore-exact-unchanged-candidate-once', 'version': version}), flush=True)
                run('native-reinstall-once', ['dpkg', '--install', str(artifact)], timeout=120)
                props = service('after-reinstall-observation')
                if props.get('Result') == 'start-limit-hit':
                    run('isolate-only-owned-start-budget', ['systemctl', 'reset-failed', UNIT])
                    run('start-only-owned-restored-unit', ['systemctl', 'start', UNIT])
                report['final_ready'] = ready('restored')
                report['after_restore'] = snapshot()
                if report['after_restore'] != report['before'] or report['final_ready']['count'] != 760:
                    raise RuntimeError('Restored package changed retained state')
                if run('final-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+version:
                    raise RuntimeError('Exact candidate restoration not configured')
                audit_installed(candidate, version)
                report['restore_passed'] = True
                check('EXACT_CANDIDATE_REINSTALLED_READY_SAME_ENDPOINT760_AND_ALL_RETAINED_STATE', url=URL, pid=int(report['final_ready']['service']['MainPID']))
            except BaseException as restore_failure:
                report['restore_error'] = {'type': type(restore_failure).__name__, 'message': str(restore_failure)}
                (work/'restore-error.log').write_text(traceback.format_exc().replace(token, '[REDACTED]') if token else traceback.format_exc())
        run('owned-unit-journal', ['journalctl', '-u', UNIT, '-b', '--no-pager', '-n', '160', '-o', 'short-iso'], expected=None)
        report['passed'] = bool(report.get('removal_checks_completed') and report.get('restore_passed') and not report['removal_failures'] and not report.get('error'))
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (work/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ('passed', 'removal_checks_completed', 'removal_failures', 'error', 'restore_passed', 'restore_error', 'final_ready')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
