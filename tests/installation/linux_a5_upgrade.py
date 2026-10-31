"""Exact gated R7-to-R8 A5-source upgrade of the experimental Linux API.

Default operation is read-only preflight. Installation requires the explicit
--execute-upgrade flag after the integration owner's optional-AI restore gate.
This reuses the successful R7 upgrade workflow and unchanged12-group native
runtime harness. It does not enable/configure a model or import new sources.
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
CURRENT_VERSION = '0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
CURRENT_HASH = '02229cd57f01c36391df2a966f11f9275feed9f8aacdc8dc5640766439882605'
CURRENT_SOURCE = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
VERSION = '0.4.0~alpha.1+dev20261031.r8.ac7e694e9e38-1'
ARTIFACT_HASH = 'd8b741ee36921a536a4624e4c351f8f790c89b75e9bd2bea6127a72b865dd675'
BASE_SOURCE = 'ac7e694e9e3849fb98e68878f76ac6a376f572497d071040a4da1157a41bf8f8'
EFFECTIVE_SOURCE = '1116ee30e64527c61207b6e753b71f69e37082549f76cf5e33e923d513c81158'
APPLICATION_ORIGIN = '7251f7fdded28f4f2af354313c0232a6d36cb8121d0eea746a9b3922b466566a'
CONTRACT = {'current_version': CURRENT_VERSION, 'target_version': VERSION,
            'current_artifact_sha256': CURRENT_HASH, 'target_artifact_sha256': ARTIFACT_HASH,
            'target_bytes': 2939100, 'base_source_content_sha256': BASE_SOURCE,
            'effective_source_content_sha256': EFFECTIVE_SOURCE, 'application_origin_content_sha256': APPLICATION_ORIGIN,
            'target_payload_files': 1370, 'retained_url': URL, 'retained_records': 760,
            'required_gate': 'Integration owner authorization after independent R8 extracted-candidate audit and optional-AI restore gate',
            'out_of_scope': ['Other units', 'Provider HTTP/key changes', 'Full Linux desktop/Joomla/MariaDB installation', 'Model inference claim']}
RUNTIME_HARNESS_SHA256 = '9ac2b39a0d7390c48318d43b01e83847052377502469e417a6c449eb9feb21ca'
REUSED_UPGRADE_SHA256 = 'ef7f35bd6a8981bcbfdd182ac46d0fb855ebb1fa80e86b71cf3968670c12d85d'
MODEL_UNIT = 'dragonhydra-local-ai.service'
MODEL_UNIT_PATH = Path('/etc/systemd/system')/MODEL_UNIT
MODEL_DIRECTORY = Path('/etc/dragonhydra/local-ai')
AI_OWNER = 'DRAGONHYDRA.optional-local-ai/1'
CONTRACT.update(application_origin_embedded_in_software=False,
                schema_policy='Retain existing columns/objects; only an absent product_jobs.next_attempt REAL NOT NULL DEFAULT0 may be appended; context schema remains lazy.',
                default_operation='read-only preflight; no backup or lifecycle commands',
                runtime_harness_sha256=RUNTIME_HARNESS_SHA256,
                reused_upgrade_harness_sha256=REUSED_UPGRADE_SHA256)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command_guard(argv, execute):
    """Refuse lifecycle/native package writes in the default preflight path."""
    argv = list(map(str, argv))
    command = Path(argv[0]).name if argv else ''
    readonly = ((command == 'systemctl' and len(argv) > 1 and argv[1] in ('show', 'is-enabled'))
                or command in ('dpkg-query', 'journalctl')
                or (command == 'dpkg' and argv[1:2] == ['--compare-versions'])
                or (command == 'sh' and argv[1:2] == ['-n']))
    if readonly:
        return
    writes = ((command == 'dpkg' and len(argv) == 3 and argv[1] == '--install'
               and argv[2] == str(ROOT/'dist/linux/native-kernel-20261031/r8'/('dragonhydra-api_'+VERSION+'_amd64.deb')))
              or (command == 'systemctl' and len(argv) == 3 and argv[1] in ('reset-failed', 'start') and argv[-1] == UNIT)
              or (command == 'python3' and len(argv) > 2 and argv[1] == '-B'
                  and argv[2] == str(ROOT/'tests/installation/linux_systemd_package.py')))
    if not execute or not writes:
        raise RuntimeError('Command is outside the explicit execution contract')


def validate_ai_state(api_service, model_service, configuration, owner=None, probe_exit=0):
    if probe_exit and not (probe_exit == 4 and model_service.get('LoadState') == 'not-found'):
        raise RuntimeError('Optional model state query failed; absence was not proven')
    if api_service.get('DropInPaths', '').strip():
        raise RuntimeError('API drop-ins remain; optional AI must be restored before this upgrade')
    if (configuration.get('configured') is not False or configuration.get('endpoint') != ''
            or configuration.get('credential_source') != 'none'):
        raise RuntimeError('API local model configuration must be empty and unconfigured')
    if model_service.get('ActiveState') != 'inactive':
        raise RuntimeError('Optional model must be inactive; preflight never stops it')
    fragment = model_service.get('FragmentPath', '')
    if fragment and (fragment != str(MODEL_UNIT_PATH) or not owner or owner.get('owner') != AI_OWNER):
        raise RuntimeError('An unrelated model unit exists; it will not be touched')
    if model_service.get('LoadState') not in ('loaded', 'not-found'):
        raise RuntimeError('Unexpected optional-model load state')
    if owner and (owner.get('owner') != AI_OWNER or owner.get('enabled') is not False):
        raise RuntimeError('Optional-model ownership must record a disabled configuration')


def database_schema(db):
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {'objects': [list(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')],
            'columns': {name: [list(row) for row in db.execute('PRAGMA table_info("'+name.replace('"','""')+'")')] for name in tables}}


def validate_schema_change(before, after):
    """Accept only the explicitly understood additive retry column, no DDL drift."""
    if set(before['columns']) != set(after['columns']):
        raise RuntimeError('Startup silently added or removed database tables')
    appended = []
    for table, columns in before['columns'].items():
        changed = after['columns'][table]
        if changed[:len(columns)] != columns:
            raise RuntimeError('Existing database columns changed: '+table)
        extra = changed[len(columns):]
        if extra:
            if (table != 'product_jobs' or len(extra) != 1 or extra[0][1:] != ['next_attempt', 'REAL', 1, '0', 0]
                    or any(column[1] == 'next_attempt' for column in columns)):
                raise RuntimeError('Unreviewed additive database columns: '+table)
            appended.append('product_jobs.next_attempt')
    old = {(row[0], row[1]): row for row in before['objects']}
    new = {(row[0], row[1]): row for row in after['objects']}
    if old.keys() != new.keys():
        raise RuntimeError('Startup silently added or removed schema objects')
    for key in old:
        if old[key] != new[key] and not (key == ('table', 'product_jobs') and appended):
            raise RuntimeError('Existing schema object changed: '+str(key))
    required = {'status', 'attempts', 'cancel_requested', 'deadline', 'lease_until', 'heartbeat', 'next_attempt'}
    if not required <= {row[1] for row in after['columns'].get('product_jobs', [])}:
        raise RuntimeError('Required durable job-claim columns are absent')
    return {'allowed_appended_columns': appended, 'context_tables_added': False,
            'job_claim_columns_present': True, 'other_schema_unchanged': True}


def finalize_status(boundary, report, artifact):
    """Prepare the metadata consumer's status only from this actual run."""
    commands = report['commands']
    upgrade = next((item for item in commands if item['name'] == 'native-r7-to-r8-upgrade-once'), None)
    comparison = next((item for item in commands if item['name'] == 'native-mandatory-version-increase'), None)
    runtime_path = boundary/'runtime/verification.json'
    runtime = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {}
    crash = next((item for item in runtime.get('checks', []) if item['name'] == 'Systemd Restart=on-failure recovers exactly owned failed process'), None)
    xlsx = next((item for item in runtime.get('checks', []) if item['name'] == 'Actual installed-system Excel workbook downloaded and validated'), None)
    status = {'schema_version': 1, 'status': 'FROZEN_APPLICATION_UPGRADE_AND_RUNTIME_VERIFIED' if report['passed'] else 'FAILED_RETAINED_EVIDENCE_NO_RETRY',
        'passed': report['passed'], 'observed_at': report['finished_at'], 'target': 'Ubuntu26.04.1 x86_64 / WSL2 / CPython3.14',
        'scope': 'Native API component only; no complete Linux workstation, clean-machine, desktop, local-model or fresh-provider claim',
        'artifact': {'filename': artifact.name, 'bytes': artifact.stat().st_size, 'sha256': digest(artifact), 'signing': 'Unsigned development Debian package'},
        'frozen_contract': CONTRACT, 'native_upgrade': upgrade, 'native_version_comparison': comparison,
        'native_upgrade_attempts': report['installed_attempts'],
        'retained_public_rows_raw_evidence_pairing_configuration_cache_protections_unchanged': bool(report.get('passed')),
        'installed_runtime': {'passed': runtime.get('passed', False), 'functional_groups': len(runtime.get('checks', [])),
            'endpoint_persistent': runtime.get('endpoint_persistent'), 'endpoint_history': runtime.get('endpoint_history', []),
            'records_before': runtime.get('persistence', {}).get('before', {}).get('count'),
            'records_after': runtime.get('persistence', {}).get('after', {}).get('count'),
            'controlled_failure': crash, 'xlsx': xlsx, 'gaps': runtime.get('gaps', []), 'source_report': 'runtime/verification.json'},
        'last_observed_ready': report.get('final_ready'), 'private_backup_acl_verified': bool(report.get('private_backup')),
        'raw_tokens_or_configuration_files_backed_up': False, 'provider_network_or_keys_changed': False,
        'optional_ai_configuration_preserved': report.get('optional_ai_before') == report.get('optional_ai_after') if 'optional_ai_before' in report else False,
        'local_model_inference_tested': False, 'schema_migration': report.get('schema_migration'),
        'context_reader': report.get('context_reader'), 'limits': report.get('limitations', []), 'source_report': 'run/verification.json'}
    (boundary/'STATUS.json').write_text(json.dumps(status, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--expected-base-source', required=True)
    parser.add_argument('--expected-effective-source', required=True)
    parser.add_argument('--expected-application-origin', required=True)
    parser.add_argument('--execute-upgrade', action='store_true', help='Explicit integration-owner gate: apply exactly one upgrade, then run the12-group installed-unit acceptance; otherwise read-only preflight')
    args = parser.parse_args()
    for name, value, expected in (
        ('base', args.expected_base_source, BASE_SOURCE),
        ('effective', args.expected_effective_source, EFFECTIVE_SOURCE),
        ('application origin', args.expected_application_origin, APPLICATION_ORIGIN),
    ):
        if not re.fullmatch('[a-f0-9]{64}', value) or value != expected:
            parser.error('Explicit '+name+' source must match the complete frozen R8 contract SHA256')
    artifact, work = args.artifact.resolve(), args.work.resolve()
    boundary = ROOT/'build/linux/native-kernel-20261031/system-install-8'
    if (platform.system() != 'Linux' or os.getuid() != 0 or work.exists() or (work != boundary/'run' if args.execute_upgrade else (work.parent != boundary or not re.fullmatch(r'preflight-[1-9][0-9]*', work.name)))
            or artifact != ROOT/'dist/linux/native-kernel-20261031/r8'/('dragonhydra-api_'+VERSION+'_amd64.deb')):
        raise SystemExit('Native root, exact frozen artifact and fresh system-install-8/run (apply) or preflight-N (read-only) required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    (work/'CONTRACT.json').write_text(json.dumps(CONTRACT, indent=2)+'\n')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False, 'contract': CONTRACT,
              'harness_sha256': digest(__file__), 'commands': [], 'checks': [], 'installed_attempts': 0,
              'mode': 'execute-upgrade' if args.execute_upgrade else 'read-only-preflight',
              'scope': 'Frozen-source R7-to-R8 native API component upgrade on existing Ubuntu26.04/WSL only; no context payload ingestion or model compatibility claim'}
    token = ''
    opener = build_opener(ProxyHandler({}))

    def run(name, argv, expected=0, timeout=60):
        command_guard(argv, args.execute_upgrade)
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
                            '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result', '-p', 'NRestarts', '-p', 'DropInPaths'])
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
            db.execute('BEGIN')
            schema = database_schema(db)
            pending = db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running','interrupted')").fetchone()[0]
            if pending:
                raise RuntimeError('Pending jobs exist; refusing upgrade or restart of active work')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Operational database integrity check failed')
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            logical = {}
            for table in sorted(tables):
                if not re.fullmatch('public_[a-z_]+', table):
                    raise RuntimeError('Unexpected public table name')
                count = len(db.execute('PRAGMA table_info("'+table+'")').fetchall())
                rows = db.execute('SELECT * FROM "'+table+'" ORDER BY '+','.join(map(str, range(1, count+1)))).fetchall()
                data = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b: {'bytes_hex': b.hex()}).encode()
                logical[table] = {'rows': len(rows), 'sha256': hashlib.sha256(data).hexdigest()}
            other = {}
            for name in sorted(schema['columns']):
                if not re.fullmatch(r'connector_[a-z_]+|cognitive_records|cognitive_receipts', name):
                    continue
                count = len(schema['columns'][name])
                rows = db.execute('SELECT * FROM "'+name+'" ORDER BY '+','.join(map(str, range(1,count+1)))).fetchall()
                body = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b: {'bytes_hex':b.hex()}).encode()
                other[name] = {'rows': len(rows), 'sha256': hashlib.sha256(body).hexdigest()}
        raw = [{'path': p.relative_to(STATE).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}
               for p in sorted((STATE/'raw').rglob('*')) if p.is_file()]
        files = {}
        for path in (Path('/etc/dragonhydra/api.env'), STATE/'local-session.json', STATE/'managed-port.json'):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError('Protected retained configuration/session/cache must be native regular0600 files')
            files[str(path)] = {'sha256': digest(path), 'mode': '0600', 'uid': info.st_uid, 'gid': info.st_gid}
        if stat.S_IMODE(STATE.stat().st_mode) != 0o700:
            raise RuntimeError('Native state directory protection must remain0700')
        return {'public_tables': logical, 'connector_and_cognitive_tables': other,
                'raw_evidence': raw, 'protected_files': files, 'schema': schema,
                'pairing_sha256': hashlib.sha256(token.encode()).hexdigest()}

    def optional_ai_snapshot(props, phase):
        child = run(phase+'-optional-model', ['systemctl', 'show', MODEL_UNIT, '-p', 'ActiveState', '-p', 'LoadState', '-p', 'FragmentPath', '-p', 'UnitFileState'], expected=None)
        model = dict(line.split('=', 1) for line in child.stdout.splitlines() if '=' in line)
        owner = None
        files = {}
        if MODEL_DIRECTORY.exists():
            directory = MODEL_DIRECTORY.lstat()
            if not stat.S_ISDIR(directory.st_mode) or stat.S_IMODE(directory.st_mode) != 0o700 or directory.st_uid or directory.st_gid:
                raise RuntimeError('Optional-AI configuration directory lacks native root0700 protection')
            allowed = {'key', 'api.env', 'ownership.json', 'configure.lock'}
            if any(path.name not in allowed for path in MODEL_DIRECTORY.iterdir()):
                raise RuntimeError('Unrecognized optional-AI configuration file; preserve and review')
            marker = MODEL_DIRECTORY/'ownership.json'
            if not marker.is_file() or marker.is_symlink():
                raise RuntimeError('Optional-AI files lack an explicit ownership marker')
            owner = json.loads(marker.read_text())
        paths = ([*MODEL_DIRECTORY.iterdir()] if MODEL_DIRECTORY.exists() else [])
        paths += [MODEL_UNIT_PATH, Path('/opt/dragonhydra/local-ai/profiles/qwen3-4b-q4_k_m.json'), STATE/'local-ai.json']
        for path in paths:
            if not path.exists() and not path.is_symlink():
                continue
            info = path.lstat()
            expected_mode = 0o600 if path.parent in (MODEL_DIRECTORY, STATE) else 0o644
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != expected_mode:
                raise RuntimeError('Unexpected optional-AI file type or permissions')
            if path.parent != STATE and (info.st_uid or info.st_gid):
                raise RuntimeError('Optional-AI configuration/profile is not root-owned')
            files[str(path)] = {'sha256': digest(path), 'mode': oct(expected_mode), 'uid': info.st_uid, 'gid': info.st_gid}
        configuration = request('/local-model/configuration')
        validate_ai_state(props, model, configuration, owner, child.returncode)
        if MODEL_UNIT_PATH.exists() and not MODEL_UNIT_PATH.read_bytes().startswith(('# '+AI_OWNER+'\n').encode()):
            raise RuntimeError('Optional model unit does not contain the explicit owner header')
        return {'files': files, 'api_configuration': configuration, 'model_state': model,
                'disabled_owned_configuration_preserved': bool(owner), 'no_model_action_performed': True}

    def compare_retained(before, after):
        schema = validate_schema_change(before['schema'], after['schema'])
        if {key: value for key, value in before.items() if key != 'schema'} != {key: value for key, value in after.items() if key != 'schema'}:
            raise RuntimeError('Upgrade changed committed public rows, raw evidence, pairing, cache or configuration protections')
        return schema

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
        if (platform.python_version_tuple()[:2] != ('3', '14')
                or 'VERSION_ID="26.04"' not in Path('/etc/os-release').read_text()):
            raise RuntimeError('Only native Ubuntu26.04 / CPython3.14 is declared for this gate')
        runtime_harness = ROOT/'tests/installation/linux_systemd_package.py'
        if digest(runtime_harness) != RUNTIME_HARNESS_SHA256 or digest(ROOT/'tests/installation/linux_frozen_upgrade.py') != REUSED_UPGRADE_SHA256:
            raise RuntimeError('Successful source/runtime harness changed; review before reuse')
        extracted = json.loads((ROOT/'build/linux/native-kernel-20261031/acceptance-8/verification.json').read_text())
        audited = json.loads((ROOT/'build/linux/native-kernel-20261031/artifact-audit-8/verification.json').read_text())
        context_proof = json.loads((ROOT/'build/linux/native-kernel-20261031/context-8/run-r1/verification.json').read_text())
        if (not extracted['passed'] or len(extracted['checks']) != 9 or extracted['artifact']['sha256'] != ARTIFACT_HASH
                or not audited['passed'] or audited['findings'] or len(audited['checks']) != 16
                or not context_proof['passed'] or context_proof['effective_source_content_sha256'] != EFFECTIVE_SOURCE):
            raise RuntimeError('Independent exact R8 extracted/archive/context-reader gates are absent')
        report['reused_proofs'] = {'extracted_groups': 9, 'archive_audit_groups': 16,
            'extracted_context_reader_groups': 4, 'context_payload_ingestion_tested': False}
        current_artifact = ROOT/'dist/linux/native-kernel-20261031/r7'/('dragonhydra-api_'+CURRENT_VERSION+'_amd64.deb')
        if digest(current_artifact) != CURRENT_HASH or artifact.stat().st_size != CONTRACT['target_bytes'] or digest(artifact) != ARTIFACT_HASH:
            raise RuntimeError('Exact current/candidate frozen archive mismatch')
        if run('current-dpkg-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+CURRENT_VERSION:
            raise RuntimeError('Existing installed package differs from exact R7 checkpoint')
        run('native-mandatory-version-increase', ['dpkg', '--compare-versions', VERSION, 'gt', CURRENT_VERSION])
        for name in (str(PREFIX/'BUILD-IDENTITY.json'), '/usr/lib/systemd/system/'+UNIT):
            if run('package-owner-'+Path(name).name, ['dpkg-query', '-S', name]).stdout.strip() != 'dragonhydra-api: '+name:
                raise RuntimeError('Package-owned path guard failed')
        old_payload = archive_members(current_artifact, '--fsys-tarfile', 'old-r7-native-payload')
        new_payload = archive_members(artifact, '--fsys-tarfile', 'new-r8-native-payload')
        old_control = archive_members(current_artifact, '--ctrl-tarfile', 'old-r7-native-control')
        new_control = archive_members(artifact, '--ctrl-tarfile', 'new-r8-native-control')
        if len(old_payload) != 1367 or len(new_payload) != 1370:
            raise RuntimeError('Unexpected current/candidate payload file count')
        audit_installed(old_payload)
        old_identity = json.loads(old_payload['opt/dragonhydra/api/BUILD-IDENTITY.json']['payload'])
        new_identity = json.loads(new_payload['opt/dragonhydra/api/BUILD-IDENTITY.json']['payload'])
        if (old_identity['source_content_sha256'] != CURRENT_SOURCE or new_identity['source_content_sha256'] != EFFECTIVE_SOURCE
                or new_identity['base_source_content_sha256'] != BASE_SOURCE or new_identity['debian_version'] != VERSION
                or new_identity['api_namespace'] != '/dragon/api/v1' or new_identity['schema_version_api'] != 1
                or old_identity['dependencies'] != new_identity['dependencies']):
            raise RuntimeError('Frozen source/API/schema/dependency identity mismatch')
        for filename, expected in (('SOURCE-MANIFEST.json', BASE_SOURCE), ('EFFECTIVE-SOURCE-MANIFEST.json', EFFECTIVE_SOURCE)):
            manifest = json.loads(new_payload['usr/share/doc/dragonhydra-api/'+filename]['payload'])
            actual = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            if actual != expected or manifest['source_content_sha256'] != expected:
                raise RuntimeError('Frozen origin/source manifest mismatch: '+filename)
        windows = ROOT/'build/connections/payload-20261031-a5-r2'
        origin = json.loads((windows/'SOURCE-MANIFEST.json').read_text())
        origin_hash = hashlib.sha256(json.dumps(origin['files'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        base = json.loads(new_payload['usr/share/doc/dragonhydra-api/SOURCE-MANIFEST.json']['payload'])
        base_files = {item['path']: item for item in base['files'] if item['path'].startswith('src/dragonhydra/')}
        origin_files = {item['path']: item for item in origin['files'] if item['path'].startswith('src/dragonhydra/')}
        if (origin_hash != APPLICATION_ORIGIN or origin['content_sha256'] != APPLICATION_ORIGIN
                or len(origin['files']) != 67 or len(base['files']) != 70 or len(base_files) != 60 or base_files != origin_files
                or 'application_snapshot_sha256' in new_identity):
            raise RuntimeError('Separately verified complete A5 Windows origin does not match packaged application')
        for item in origin['files']:
            path = windows/'source'/item['path']
            if path.is_symlink() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                raise RuntimeError('Frozen external Windows source changed')
        report['application_origin'] = {'content_sha256': APPLICATION_ORIGIN, 'files': 67, 'application_files': 60,
                                        'origin_embedded_in_software': False}
        control_text = new_control['control']['payload'].decode()
        if 'Package: dragonhydra-api\n' not in control_text or 'Version: '+VERSION+'\n' not in control_text:
            raise RuntimeError('Candidate native control version mismatch')
        for script in ('preinst', 'postinst', 'prerm', 'postrm'):
            if new_control[script]['payload'] != old_control[script]['payload']:
                raise RuntimeError('Unreviewed lifecycle-script change from verified R7: '+script)
            path = work/script
            path.write_bytes(new_control[script]['payload'])
            run(script+'-shell-syntax', ['sh', '-n', str(path)])
        report['before_ready'] = ready('r7-baseline')
        if json.loads((STATE/'managed-port.json').read_text()).get('port') != 55971:
            raise RuntimeError('Saved managed endpoint changed from55971')
        report['optional_ai_before'] = optional_ai_snapshot(report['before_ready']['service'], 'before')
        report['before'] = snapshot()
        validate_schema_change(report['before']['schema'], report['before']['schema'])
        check('Read-only R7 ownership,760records/pairing/saved55971 and disabled optional-AI baseline verified')
        report['preflight_passed'] = True
        if not args.execute_upgrade:
            report['passed'] = True
            report['host_changes_performed'] = False
            return 0
        private = boundary/'private-evidence'
        marker = private/'ACL-RESTRICTED.json'
        if not marker.is_file():
            raise RuntimeError('A Windows-ACL-restricted project backup directory must be prepared')
        acl = json.loads(marker.read_text())
        if (acl.get('restricted') is not True or acl.get('inheritance_protected') is not True
                or set(acl.get('allowed_sids', [])) != {'S-1-5-18', acl.get('current_user_sid')}
                or acl.get('no_token_or_configuration_backup') is not True):
            raise RuntimeError('Backup ACL observation does not prove the explicit restricted Windows directory')
        backup = private/'core-r7-before-upgrade.sqlite3'
        if backup.exists():
            raise RuntimeError('Preserve existing private backup')
        with closing(sqlite3.connect('file:'+str(STATE/'core.sqlite3')+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Consistent SQLite backup failed')
            if database_schema(target) != report['before']['schema']:
                raise RuntimeError('Backup schema does not match the pre-upgrade snapshot')
            for name, expected in {**report['before']['public_tables'], **report['before']['connector_and_cognitive_tables']}.items():
                columns = len(target.execute('PRAGMA table_info("'+name+'")').fetchall())
                rows = target.execute('SELECT * FROM "'+name+'" ORDER BY '+','.join(map(str, range(1,columns+1)))).fetchall()
                body = json.dumps(rows, ensure_ascii=False, separators=(',', ':'), default=lambda b: {'bytes_hex':b.hex()}).encode()
                if len(rows) != expected['rows'] or hashlib.sha256(body).hexdigest() != expected['sha256']:
                    raise RuntimeError('Backup public logical rows differ')
        if snapshot() != report['before']:
            raise RuntimeError('Concurrent state changes occurred while taking backup; no package operation performed')
        report['private_backup'] = {'path': 'private-evidence/core-r7-before-upgrade.sqlite3', 'sha256': digest(backup), 'token_config_files_not_copied': True}
        check('Frozen R7/R8 identities,1370candidate files,4unchanged scripts and native version increase verified')
        report['preflight_passed'] = True
        report['installed_attempts'] = 1
        print(json.dumps({'stage': 'native-r7-to-r8-upgrade-start'}), flush=True)
        run('native-r7-to-r8-upgrade-once', ['dpkg', '--install', str(artifact)], timeout=150)
        current = owned_service('post-upgrade-owned-service')
        if current.get('Result') == 'start-limit-hit':
            run('isolate-owned-upgrade-start-budget', ['systemctl', 'reset-failed', UNIT])
            run('start-only-owned-upgraded-unit', ['systemctl', 'start', UNIT])
        report['after_ready'] = ready('r8-upgraded')
        report['after'] = snapshot()
        report['schema_migration'] = compare_retained(report['before'], report['after'])
        report['optional_ai_after'] = optional_ai_snapshot(report['after_ready']['service'], 'after')
        if report['optional_ai_before'] != report['optional_ai_after']:
            raise RuntimeError('Upgrade changed disabled optional-AI files or state')
        reader_before = snapshot()
        first_match = request('/matches?limit=1')['items'][0]['id']
        for suffix in ('source-context', 'source-events?offset=0&limit=20'):
            answer = request('/matches/'+first_match+'/'+suffix)
            if answer.get('supported') is not False or answer.get('availability') != 'unsupported':
                raise RuntimeError('Non-StatsBomb retained match must report unsupported source context')
        if snapshot() != reader_before:
            raise RuntimeError('New installed context reader GET silently changed schema or retained data')
        report['context_reader'] = {'actual_installed_gets': 2, 'availability': 'unsupported',
                                    'schema_and_data_unchanged': True, 'context_payload_ingestion_tested': False,
                                    'supported_not_requested_verified_separately': 'context-8/run-r1/verification.json'}
        check('Installed A5 context readers preserve schema and rows; disabled optional-AI files unchanged')
        audit_installed(new_payload)
        if run('upgraded-dpkg-version', ['dpkg-query', '-W', '-f=${Status}\n${Version}', 'dragonhydra-api']).stdout.strip() != 'install ok installed\n'+VERSION:
            raise RuntimeError('Exact R8 not configured')
        report['upgrade_passed'] = True
        check('Actual same-endpoint R8 upgrade preserves all760 records and retained hashes')
        if digest(runtime_harness) != RUNTIME_HARNESS_SHA256:
            raise RuntimeError('Runtime harness changed after preflight; no lifecycle acceptance run')
        run('r8-installed-runtime-acceptance', ['/usr/bin/python3', '-B', str(ROOT/'tests/installation/linux_systemd_package.py'),
            '--expected-version', VERSION, '--expected-base-source', BASE_SOURCE, '--expected-effective-source', EFFECTIVE_SOURCE,
            '--work', str(boundary/'runtime')], timeout=180)
        runtime = json.loads((boundary/'runtime/verification.json').read_text())
        if not runtime['passed'] or not runtime['functional_checks_passed'] or len(runtime['checks']) != 12 or set(runtime['endpoint_history']) != {URL}:
            raise RuntimeError('Changed application failed installed-runtime acceptance')
        report['runtime'] = {'passed': True, 'groups': len(runtime['checks']), 'report': '../runtime/verification.json', 'endpoint_history': runtime['endpoint_history']}
        report['final_ready'] = ready('final-r8')
        report['final_snapshot'] = snapshot()
        compare_retained(report['before'], report['final_snapshot'])
        if optional_ai_snapshot(report['final_ready']['service'], 'final') != report['optional_ai_before']:
            raise RuntimeError('Installed lifecycle tests changed optional AI configuration')
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
        if args.execute_upgrade:
            finalize_status(boundary, report, artifact)
    print(json.dumps({key: report.get(key) for key in ('passed', 'preflight_passed', 'upgrade_passed', 'runtime', 'error', 'last_observed_service')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
