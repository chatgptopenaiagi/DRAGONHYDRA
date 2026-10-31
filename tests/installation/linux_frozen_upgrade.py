"""Exact gated R6-to-R7 frozen-source upgrade of the experimental Linux API.

Preparation is inert. A native installation requires --execute-upgrade after
the integration owner approves the independent extracted-candidate audit.
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
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[2]
PREFIX = Path('/opt/dragonhydra/api')
STATE = Path('/var/lib/dragonhydra-api')
UNIT = 'dragonhydra-api.service'
URL = 'http://127.0.0.1:55971'
CURRENT_VERSION = '0.4.0~alpha.1+dev20261031.9f3d6e5ab108-6'
CURRENT_HASH = 'a1719e316638b8df4e9a5b463a36d49c2037b86607c7c574b47d4561f14bad05'
CURRENT_SOURCE = '6ceb72702f628c5be0a9440e5b12022e73e74bed95883be1c8d3ceabfc203b5a'
VERSION = '0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
ARTIFACT_HASH = '02229cd57f01c36391df2a966f11f9275feed9f8aacdc8dc5640766439882605'
BASE_SOURCE = 'c77ddb3667f282407885e29a6d2a7b37c7b180d28672412771b5f616db4bb35a'
EFFECTIVE_SOURCE = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
APPLICATION_ORIGIN = '8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5'
CONTRACT = {'current_version': CURRENT_VERSION, 'target_version': VERSION,
            'current_artifact_sha256': CURRENT_HASH, 'target_artifact_sha256': ARTIFACT_HASH,
            'target_bytes': 2924088, 'base_source_content_sha256': BASE_SOURCE,
            'effective_source_content_sha256': EFFECTIVE_SOURCE, 'application_origin_content_sha256': APPLICATION_ORIGIN,
            'target_payload_files': 1367, 'retained_url': URL, 'retained_records': 760,
            'required_gate': 'Integration owner authorization after independent R7 extracted-candidate audit',
            'out_of_scope': ['Other units', 'Provider HTTP/key changes', 'Full Linux desktop/Joomla/MariaDB installation', 'Model inference claim']}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--expected-base-source', required=True)
    parser.add_argument('--expected-effective-source', required=True)
    parser.add_argument('--expected-application-origin', required=True)
    parser.add_argument('--execute-upgrade', action='store_true')
    args = parser.parse_args()
    for name, value, expected in (
        ('base', args.expected_base_source, BASE_SOURCE),
        ('effective', args.expected_effective_source, EFFECTIVE_SOURCE),
        ('application origin', args.expected_application_origin, APPLICATION_ORIGIN),
    ):
        if not re.fullmatch('[a-f0-9]{64}', value) or value != expected:
            parser.error('Explicit '+name+' source must match the complete frozen R7 contract SHA256')
    if not args.execute_upgrade:
        parser.error('No host operation performed. Explicit integration-owner gate and --execute-upgrade are required.')
    artifact, work = args.artifact.resolve(), args.work.resolve()
    boundary = ROOT/'build/linux/native-kernel-20261031/system-install-7'
    if (platform.system() != 'Linux' or os.getuid() != 0 or work.exists() or work != boundary/'run'
            or artifact != ROOT/'dist/linux/native-kernel-20261031/r7'/('dragonhydra-api_'+VERSION+'_amd64.deb')):
        raise SystemExit('Native root, exact frozen artifact and fresh owned system-install-7/run required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    (work/'CONTRACT.json').write_text(json.dumps(CONTRACT, indent=2)+'\n')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False, 'contract': CONTRACT,
              'harness_sha256': digest(__file__), 'commands': [], 'checks': [], 'installed_attempts': 0,
              'scope': 'Frozen-source R6-to-R7 native API component upgrade on existing Ubuntu26.04/WSL only'}
    token = ''
    opener = build_opener(ProxyHandler({}))

    def run(name, argv, expected=0, timeout=60):
        begun = time.monotonic()
        child = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                               env={**os.environ, 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'DEBIAN_FRONTEND': 'noninteractive'})
        for stream, value in [('stdout', child.stdout), ('stderr', child.stderr)]:
            (work/(name+'.'+stream+'.log')).write_text(value.replace(token, '[REDACTED]') if token else value)
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if expected is not None and child.returncode != expected:
            raise RuntimeError(name+' exit'+str(child.returncode)+'; inspect exact native log')
        return child

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name, **details}), flush=True)

    def owned_service(name):
        result = run(name, ['systemctl', 'show', UNIT, '-p', 'FragmentPath', '-p', 'DynamicUser', '-p', 'ExecStart',
                            '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result', '-p', 'NRestarts'])
        props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if (props.get('FragmentPath') != '/usr/lib/systemd/system/'+UNIT or props.get('DynamicUser') != 'yes'
                or str(PREFIX/'bin/dragonhydra-server') not in props.get('ExecStart', '')
                or '--state '+str(STATE) not in props.get('ExecStart', '')):
            raise RuntimeError('Exact package-owned unit/process/state guard failed')
        return props

    def request(path):
        with opener.open(Request(URL+'/dragon/api/v1'+path, headers={'Authorization': 'Bearer '+token}), timeout=3) as response:
            return json.load(response)

    def ready(phase):
        nonlocal token
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            props = owned_service(phase+'-service')
            try:
                endpoint = json.loads((STATE/'endpoint.json').read_text())
                if props.get('ActiveState') == 'active' and endpoint['pid'] == int(props['MainPID']) and endpoint['url'] == URL:
                    token = json.loads((STATE/'local-session.json').read_text())['token']
                    if request('/health/ready')['status'] == 'ready':
                        count = request('/matches?limit=1')['total']
                        if count != 760:
                            raise RuntimeError('Existing retained match count differs')
                        return {'service': props, 'url': URL, 'count': count}
            except (OSError, ValueError, URLError):
                pass
            if props.get('ActiveState') == 'failed':
                raise RuntimeError('Exact owned unit failed: '+props.get('Result', ''))
            time.sleep(.2)
        raise RuntimeError('Exact retained endpoint readiness deadline exceeded')

    def snapshot():
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            logical = {}
            for table in sorted(tables):
                if not re.fullmatch('public_[a-z_]+', table):
                    raise RuntimeError('Unexpected public table name')
                count = len(db.execute('PRAGMA table_info("'+table+'")').fetchall())
                rows = db.execute('SELECT * FROM "'+table+'" ORDER BY '+','.join(map(str, range(1, count+1)))).fetchall()
                data = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b: {'bytes_hex': b.hex()}).encode()
                logical[table] = {'rows': len(rows), 'sha256': hashlib.sha256(data).hexdigest()}
        raw = [{'path': p.relative_to(STATE).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}
               for p in sorted((STATE/'raw').rglob('*')) if p.is_file()]
        files = {}
        for path in (Path('/etc/dragonhydra/api.env'), STATE/'local-session.json', STATE/'managed-port.json'):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError('Protected retained configuration/session/cache must be native regular0600 files')
            files[str(path)] = {'sha256': digest(path), 'mode': '0600', 'uid': info.st_uid, 'gid': info.st_gid}
        return {'public_tables': logical, 'raw_evidence': raw, 'protected_files': files,
                'pairing_sha256': hashlib.sha256(token.encode()).hexdigest()}

    def archive_members(path, option, label):
        argv = ['dpkg-deb', option, str(path)]
        begun = time.monotonic()
        child = subprocess.run(argv, capture_output=True, timeout=30)
        report['commands'].append({'name': label, 'argv': argv, 'exit_code': child.returncode,
                                   'seconds': round(time.monotonic()-begun, 3)})
        if child.returncode:
            raise RuntimeError('Native archive reader failed')
        files = {}
        with tarfile.open(fileobj=io.BytesIO(child.stdout), mode='r:') as archive:
            for member in archive:
                name = PurePosixPath(member.name.removeprefix('./'))
                if name.is_absolute() or '..' in name.parts or '\\' in str(name) or member.uid or member.gid or not (member.isdir() or member.isfile()):
                    raise RuntimeError('Unsafe native archive member')
                if member.isdir():
                    if member.mode != 0o755:
                        raise RuntimeError('Unexpected native directory mode')
                    continue
                if str(name) in files:
                    raise RuntimeError('Duplicate native archive file')
                expected_mode = (0o755 if option == '--ctrl-tarfile' and name.name in ('preinst', 'postinst', 'prerm', 'postrm')
                                 or str(name) == 'opt/dragonhydra/api/bin/dragonhydra-server'
                                 else 0o600 if str(name) == 'etc/dragonhydra/api.env' else 0o644)
                if member.mode != expected_mode:
                    raise RuntimeError('Native archive mode mismatch')
                files[str(name)] = {'payload': archive.extractfile(member).read(), 'mode': member.mode}
        return files

    def audit_installed(files):
        for name, entry in files.items():
            path = Path('/')/name
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or path.read_bytes() != entry['payload'] or stat.S_IMODE(info.st_mode) != entry['mode']
                    or info.st_uid or info.st_gid):
                raise RuntimeError('Installed native payload mismatch: '+name)

    try:
        current_artifact = ROOT/'dist/linux/native-kernel-20261031/r6'/('dragonhydra-api_'+CURRENT_VERSION+'_amd64.deb')
        if digest(current_artifact) != CURRENT_HASH or artifact.stat().st_size != CONTRACT['target_bytes'] or digest(artifact) != ARTIFACT_HASH:
            raise RuntimeError('Exact current/candidate frozen archive mismatch')
        if run('current-dpkg-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+CURRENT_VERSION:
            raise RuntimeError('Existing installed package differs from exact R6 checkpoint')
        run('native-mandatory-version-increase', ['dpkg', '--compare-versions', VERSION, 'gt', CURRENT_VERSION])
        for name in (str(PREFIX/'BUILD-IDENTITY.json'), '/usr/lib/systemd/system/'+UNIT):
            if run('package-owner-'+Path(name).name, ['dpkg-query', '-S', name]).stdout.strip() != 'dragonhydra-api: '+name:
                raise RuntimeError('Package-owned path guard failed')
        old_payload = archive_members(current_artifact, '--fsys-tarfile', 'r6-native-payload')
        new_payload = archive_members(artifact, '--fsys-tarfile', 'r7-native-payload')
        old_control = archive_members(current_artifact, '--ctrl-tarfile', 'r6-native-control')
        new_control = archive_members(artifact, '--ctrl-tarfile', 'r7-native-control')
        if len(old_payload) != 1363 or len(new_payload) != 1367:
            raise RuntimeError('Unexpected current/candidate payload file count')
        audit_installed(old_payload)
        old_identity = json.loads(old_payload['opt/dragonhydra/api/BUILD-IDENTITY.json']['payload'])
        new_identity = json.loads(new_payload['opt/dragonhydra/api/BUILD-IDENTITY.json']['payload'])
        if (old_identity['source_content_sha256'] != CURRENT_SOURCE or new_identity['source_content_sha256'] != EFFECTIVE_SOURCE
                or new_identity['base_source_content_sha256'] != BASE_SOURCE or new_identity['debian_version'] != VERSION
                or new_identity['api_namespace'] != '/dragon/api/v1' or new_identity['schema_version_api'] != 1
                or old_identity['dependencies'] != new_identity['dependencies']):
            raise RuntimeError('Frozen source/API/schema/dependency identity mismatch')
        for filename, expected in (('SOURCE-MANIFEST.json', BASE_SOURCE), ('EFFECTIVE-SOURCE-MANIFEST.json', EFFECTIVE_SOURCE),
                                   ('A4-ORIGIN-SOURCE-MANIFEST.json', APPLICATION_ORIGIN)):
            manifest = json.loads(new_payload['usr/share/doc/dragonhydra-api/'+filename]['payload'])
            actual = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            field = 'content_sha256' if filename == 'A4-ORIGIN-SOURCE-MANIFEST.json' else 'source_content_sha256'
            if actual != expected or manifest[field] != expected:
                raise RuntimeError('Frozen origin/source manifest mismatch: '+filename)
        control_text = new_control['control']['payload'].decode()
        if 'Package: dragonhydra-api\n' not in control_text or 'Version: '+VERSION+'\n' not in control_text:
            raise RuntimeError('Candidate native control version mismatch')
        for script in ('preinst', 'postinst', 'prerm', 'postrm'):
            if new_control[script]['payload'] != old_control[script]['payload']:
                raise RuntimeError('Unreviewed lifecycle-script change from verified R6: '+script)
            path = work/script
            path.write_bytes(new_control[script]['payload'])
            run(script+'-shell-syntax', ['sh', '-n', str(path)])
        report['before_ready'] = ready('r6-baseline')
        report['before'] = snapshot()
        private = boundary/'private-evidence'
        if not (private/'ACL-RESTRICTED.json').is_file():
            raise RuntimeError('A Windows-ACL-restricted project backup directory must be prepared')
        backup = private/'core-r6-before-upgrade.sqlite3'
        if backup.exists():
            raise RuntimeError('Preserve existing private backup')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Consistent SQLite backup failed')
        report['private_backup'] = {'path': 'private-evidence/core-r6-before-upgrade.sqlite3', 'sha256': digest(backup), 'token_config_files_not_copied': True}
        check('Frozen R6/R7 identities,1367candidate files,4unchanged scripts and native version increase verified')
        report['preflight_passed'] = True
        report['installed_attempts'] = 1
        print(json.dumps({'stage': 'native-r6-to-r7-upgrade-start'}), flush=True)
        run('native-r6-to-r7-upgrade-once', ['dpkg', '--install', str(artifact)], timeout=150)
        current = owned_service('post-upgrade-owned-service')
        if current.get('Result') == 'start-limit-hit':
            run('isolate-owned-upgrade-start-budget', ['systemctl', 'reset-failed', UNIT])
            run('start-only-owned-upgraded-unit', ['systemctl', 'start', UNIT])
        report['after_ready'] = ready('r7-upgraded')
        report['after'] = snapshot()
        if report['before'] != report['after']:
            raise RuntimeError('Frozen-source upgrade changed retained canonical evidence/pairing/cache/config')
        audit_installed(new_payload)
        if run('upgraded-dpkg-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+VERSION:
            raise RuntimeError('Exact R7 not configured')
        report['upgrade_passed'] = True
        check('Actual same-endpoint R7 upgrade preserves all760 records and retained hashes')
        run('r7-installed-runtime-acceptance', ['/usr/bin/python3', '-B', str(ROOT/'tests/installation/linux_systemd_package.py'),
            '--expected-version', VERSION, '--expected-base-source', BASE_SOURCE, '--expected-effective-source', EFFECTIVE_SOURCE,
            '--work', str(boundary/'runtime')], timeout=180)
        runtime = json.loads((boundary/'runtime/verification.json').read_text())
        if not runtime['passed'] or not runtime['functional_checks_passed'] or set(runtime['endpoint_history']) != {URL}:
            raise RuntimeError('Changed application failed installed-runtime acceptance')
        report['runtime'] = {'passed': True, 'groups': len(runtime['checks']), 'report': '../runtime/verification.json', 'endpoint_history': runtime['endpoint_history']}
        report['final_ready'] = ready('final-r7')
        report['limitations'] = ['No provider HTTP/key configuration changed', 'No local model inference tested',
                                 'Windows DPAPI credential storage is not a Linux vault; use explicitly configured service environment keys where supported']
        report['passed'] = True
    except BaseException as failure:
        report['error'] = {'type': type(failure).__name__, 'message': str(failure)}
        (work/'error.log').write_text(traceback.format_exc().replace(token, '[REDACTED]') if token else traceback.format_exc())
    finally:
        try:
            report['last_observed_service'] = owned_service('last-owned-service')
            run('owned-unit-journal', ['journalctl', '-u', UNIT, '-b', '--no-pager', '-n', '180', '-o', 'short-iso'], expected=None)
        except BaseException as observation:
            report['observation_error'] = str(observation)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (work/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ('passed', 'preflight_passed', 'upgrade_passed', 'runtime', 'error', 'last_observed_service')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
