"""One-shot optional SQL archive acceptance. Preview is the default.

Only a reviewed, hash-bound plan may start two owned source-run server lifetimes.
No service control, SQL database drop, provider request or model download exists
in this helper. The explicit forecast uses the application's existing models.
"""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
LAB = Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB')
API = '/dragon/api/v1'
DATABASE = 'DRAGONHYDRA_CORE_NEXT_SQL_LAB'
TARGET = 'de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea'
AUTH = {'product_sessions', 'product_bridge_nonces'}
QUEUE = {'product_jobs', 'product_updates', 'sqlite_sequence'}
MODEL_NAMES = {'frequency', 'poisson_goals', 'elo', 'recency', 'ensemble'}


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(path): return sha(Path(path).read_bytes())
def gate(condition, code):
    if not condition: raise RuntimeError(code)


def ordinary(path):
    path = Path(path)
    gate(path.is_absolute() and '..' not in path.parts and path.resolve().is_relative_to(LAB.resolve()), 'LAB_PATH_REQUIRED')
    gate(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)), 'REPARSE_PATH_REJECTED')
    return path.resolve()


def read(path): return json.loads(ordinary(path).read_text(encoding='utf-8-sig'))


def typed(value):
    if isinstance(value, bytes): return {'bytes': len(value), 'sha256': sha(value)}
    if isinstance(value, Decimal): return {'decimal': str(value)}
    if isinstance(value, datetime): return {'datetime': value.isoformat()}
    if value is None or type(value) in (str, int, float, bool): return value
    return {'type': type(value).__name__, 'value': str(value)}


def sqlite_fingerprint(path):
    with closing(sqlite3.connect(ordinary(path).as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        gate(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SQLITE_SNAPSHOT_INTEGRITY_FAILED')
        objects = {kind + ':' + name: sha(canonical([kind, name, table, sql])) for kind, name, table, sql in
                   db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')}
        tables = {}
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            gate(re.fullmatch('[a-z_]+', name), 'SQLITE_TABLE_IDENTIFIER_REJECTED')
            if name in AUTH: continue
            rows = [canonical([typed(value) for value in row]) for row in db.execute('SELECT * FROM "' + name + '"')]
            gate(len(rows) <= 50000, 'SQLITE_ROW_BOUND_EXCEEDED')
            tables[name] = {'rows': len(rows), 'sha256': sha(b'\n'.join(sorted(rows)))}
        return {'schema': objects, 'tables': tables}


def source_protection(before, after, *, include_memory=False):
    allowed = AUTH | QUEUE | (set() if include_memory else {'cognitive_records', 'cognitive_receipts'})
    unchanged = all(name in after['tables'] and value == after['tables'][name]
                    for name, value in before['tables'].items() if name not in allowed)
    return (unchanged and (not include_memory or before['schema'] == after['schema'])
            and after['tables']['public_fixture_records']['rows'] == 760 and after['tables']['raw_sources']['rows'] == 2)


def normalize_clock(value):
    match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,7}))?(?:Z|\+00:00)', value)
    gate(match is not None, 'UTC_TIMESTAMP_REQUIRED')
    return match[1] + '.' + (match[2] or '').ljust(7, '0') + 'Z'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs): raise RuntimeError('LOCAL_API_REDIRECT_REJECTED')


def validate_plan(args):
    plan_path, profile_path, output = ordinary(args.plan), ordinary(args.profile), ordinary(args.output)
    plan, profile = read(plan_path), read(profile_path)
    gate(plan.get('schema_version') == 'dragonhydra.sqlserver-acceptance-plan/1', 'KNOWN_PLAN_SCHEMA_REQUIRED')
    gate(ordinary(plan['profile']) == profile_path and ordinary(plan['output']) == output, 'PLAN_PATH_BINDING_MISMATCH')
    gate(digest(profile_path) == plan['profile_sha256'], 'PROFILE_HASH_MISMATCH')
    gate(not output.exists() and output.parent.is_dir(), 'FRESH_ACCEPTANCE_OUTPUT_REQUIRED')
    gate(re.fullmatch('[a-f0-9]{40}', plan['source_commit']) and re.fullmatch('[a-f0-9]{32}', plan['nonce']), 'SOURCE_NONCE_REQUIRED')
    gate(plan['target_match'] == TARGET and plan['database'] == DATABASE, 'EXACT_ACCEPTANCE_TARGET_REQUIRED')
    gate(profile.get('source_commit') == plan['source_commit'] and profile.get('version') == plan['version'], 'PROFILE_SOURCE_VERSION_MISMATCH')
    gate(profile.get('installation_id') not in {'core-next-7ac520727b85456cac4a3a92a8dd62da', 'core-next-b447d99ab9524197af09c235077685de'}, 'EXISTING_OWNER_PROFILE_REJECTED')
    gate(Path(sys.executable).resolve() == ordinary(plan['python']) and digest(sys.executable) == plan['python_sha256'], 'EXACT_PRIVATE_PYTHON_REQUIRED')
    state = ordinary(Path(profile['state_root']) / 'kernel')
    gate(not (state / 'local-session.json').exists() and not (state / 'product.json').exists(), 'FRESH_APP_LIFETIME_REQUIRED')
    gate(digest(state / 'core.sqlite3') == plan['fixture_sha256'], 'PREPARED_FIXTURE_HASH_MISMATCH')
    gate(not (state / 'core.sqlite3-wal').exists() or (state / 'core.sqlite3-wal').stat().st_size == 0, 'CONSISTENT_FIXTURE_MAIN_REQUIRED')
    settings = read(state / 'research-storage.json')
    gate(digest(state / 'research-storage.json') == plan['research_settings_sha256'] and settings.get('provider') == 'sqlserver', 'EXPLICIT_SQL_CONFIGURATION_REQUIRED')
    gate(settings.get('sqlserver', {}).get('database') == DATABASE, 'EXACT_SQL_DATABASE_REQUIRED')
    gate(digest(ROOT / 'src/dragonhydra/build_info.json') == plan['build_info_sha256'], 'BUILD_INFO_HASH_MISMATCH')
    command = [r'C:\Program Files\Git\cmd\git.exe', '--no-optional-locks', '-C', str(ROOT)]
    environment = {key: value for key, value in os.environ.items() if key not in {'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'}}
    head = subprocess.run(command + ['rev-parse', 'HEAD'], env=environment, capture_output=True, timeout=15)
    status = subprocess.run(command + ['status', '--porcelain=v1', '--untracked-files=no'], env=environment, capture_output=True, timeout=15)
    gate(head.returncode == status.returncode == 0 and head.stdout.decode().strip() == plan['source_commit'] and not status.stdout, 'FROZEN_CLEAN_SOURCE_REQUIRED')
    return plan_path, plan, profile, state, output, settings


class Acceptance:
    def __init__(self, plan_path, plan, profile, state, output, settings):
        self.plan_path, self.plan, self.profile, self.state, self.output = plan_path, plan, profile, state, output
        self.private = output / 'private'
        self.token = None
        self.process = None
        self.streams = []
        self.port = profile['ports']['api']
        self.origin = 'http://127.0.0.1:' + str(self.port)
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.settings = settings
        self.record = {'schema_version': 'dragonhydra.sqlserver-acceptance/1', 'passed': False, 'status': 'STARTED',
            'started_at': now(), 'source_commit': plan['source_commit'], 'version': plan['version'],
            'installation_id': profile['installation_id'], 'ports': profile['ports'], 'checks': [], 'requests': [],
            'lifetimes': [], 'jobs': {}, 'automatic_retry': False, 'database_drop': False,
            'scope': 'New isolated source-run application; optional SECONDARY SQL research archive. No installer, service, GUI, provider or local-AI acceptance.'}

    def save(self):
        raw = canonical(self.record)
        gate(not self.token or self.token.encode() not in raw, 'SECRET_IN_PUBLIC_RECEIPT')
        temporary = self.output / ('receipt-' + uuid4().hex + '.tmp')
        with temporary.open('xb') as file: file.write(raw + b'\n')
        os.replace(temporary, self.output / 'verification.json')

    def check(self, name, passed, **evidence):
        self.record['checks'].append({'name': name, 'passed': bool(passed), 'observed_at': now(), **evidence})
        self.save(); gate(passed, name.upper())

    def private_json(self, name, value):
        raw = canonical(value)
        gate(not self.token or self.token.encode() not in raw, 'TOKEN_IN_RESPONSE_ARTIFACT')
        path = self.private / name
        with path.open('xb') as file: file.write(raw + b'\n')
        return {'path': str(path), 'sha256': digest(path)}

    def snapshot(self, label):
        path = self.private / (label + '.sqlite3')
        gate(not path.exists(), 'FRESH_SNAPSHOT_REQUIRED')
        deadline = time.monotonic() + 15
        with closing(sqlite3.connect((self.state / 'core.sqlite3').as_uri() + '?mode=ro', uri=True, timeout=.2)) as db, closing(sqlite3.connect(path)) as copied:
            db.backup(copied, pages=128, sleep=.01, progress=lambda *_: gate(time.monotonic() < deadline, 'SNAPSHOT_TIMEOUT'))
        value = sqlite_fingerprint(path)
        self.record.setdefault('sqlite_snapshots', {})[label] = {'path': str(path), 'sha256': digest(path), 'logical_sha256': sha(canonical(value)),
            'counts': {k: v['rows'] for k, v in value['tables'].items()}}
        self.save(); return value

    def api(self, path, *, method='GET', body=None, key=None, expected=200, anonymous=False):
        target = self.plan['target_match']
        allowed_get = {'/health/ready', '/system', '/modules', '/modules?scope=all', '/matches?limit=1', '/matches/' + target,
            '/matches/' + target + '/cognition-history', '/research/storage', '/matches/' + target + '/research/archives',
            '/matches/' + target + '/research/notes'}
        allowed = method == 'GET' and (path in allowed_get or re.fullmatch(r'/jobs/[a-f0-9]{32}|/research/archives/[a-f0-9]{64}(?:/match)?', path) is not None)
        allowed |= method == 'POST' and path in {'/research/storage/initialize', '/matches/' + target + '/forecasts',
            '/matches/' + target + '/research/archives', '/research/notes', '/system/shutdown'}
        allowed |= method == 'PUT' and re.fullmatch(r'/research/notes/[a-f0-9-]{36}', path) is not None
        gate(allowed, 'NARROW_API_OPERATION_REQUIRED')
        headers = {'Accept': 'application/json'}
        if not anonymous: headers['Authorization'] = 'Bearer ' + self.token
        if key is not None: headers['Idempotency-Key'] = key
        raw = canonical({} if body is None else body) if method in {'POST', 'PUT'} else None
        if raw is not None: headers['Content-Type'] = 'application/json'
        request = Request(self.origin + API + path, data=raw, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response: status, content = response.status, response.read(8 * 1024 * 1024 + 1)
        except HTTPError as error:
            status, content = error.code, error.read(8 * 1024 * 1024 + 1)
        gate(len(content) <= 8 * 1024 * 1024, 'BOUNDED_API_RESPONSE_REQUIRED')
        value = json.loads(content)
        self.record['requests'].append({'method': method, 'path': path, 'status': status, 'anonymous': anonymous,
            'response_sha256': sha(content), 'at': now()})
        self.save(); gate(status == expected, 'UNEXPECTED_API_STATUS_' + str(status))
        return value

    def launch(self):
        gate(len(self.record['lifetimes']) < 2 and self.process is None, 'ONLY_TWO_OWNED_LIFETIMES_ALLOWED')
        environment = {key: value for key, value in os.environ.items() if not key.startswith('DRAGONHYDRA_') and key not in
            {'OPENAI_API_KEY', 'API_FOOTBALL_KEY', 'SPORTMONKS_API_KEY', 'ODDS_API_KEY'}}
        environment.update(PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
        index = len(self.record['lifetimes']) + 1
        stream = (self.private / ('server-' + str(index) + '.log')).open('xb'); self.streams.append(stream)
        self.process = subprocess.Popen([str(sys.executable), '-B', '-m', 'dragonhydra.server', '--installation-profile', str(self.plan['profile'])],
            cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.record['lifetimes'].append({'pid': self.process.pid, 'started_at': now(), 'hidden': True})
        self.save(); deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            gate(self.process.poll() is None, 'OWNED_SERVER_EXITED_BEFORE_READY')
            token_file = self.state / 'local-session.json'
            if token_file.exists():
                self.token = read(token_file)['token']
                try:
                    ready = self.api('/health/ready')
                    if ready['status'] == 'ready':
                        system = self.api('/system')
                        identity = system['installation']
                        gate(identity['installation_id'] == self.profile['installation_id']
                            and identity['source_commit'] == self.plan['source_commit'] and identity['build_id'] == self.profile['build_id'], 'LIVE_PROFILE_SOURCE_BINDING_REQUIRED')
                        gate(system['build']['source_sha'] == self.plan['source_commit'] and system['build']['version'] == self.plan['version'], 'LIVE_BUILD_BINDING_REQUIRED')
                        return
                except (URLError, ConnectionError, TimeoutError): pass
            time.sleep(.15)
        raise RuntimeError('OWNED_SERVER_START_TIMEOUT')

    def stop(self):
        if self.process is None: return
        gate(self.process.poll() is None, 'OWNED_SERVER_EXITED_UNEXPECTEDLY')
        gate(self.token is not None, 'AUTHENTICATED_CLEANUP_TOKEN_UNAVAILABLE')
        self.api('/system/shutdown', method='POST')
        code = self.process.wait(timeout=15)
        lifetime = self.record['lifetimes'][-1]
        lifetime.update(exit_code=code, stopped_at=now())
        gate(code == 0, 'CLEAN_SHUTDOWN_EXIT_ZERO_REQUIRED')
        with socket.socket() as probe: free = probe.connect_ex(('127.0.0.1', self.port)) != 0
        lifetime['port_free'] = free; gate(free, 'OWNED_PORT_STILL_LISTENING')
        self.process = None; self.save()

    def wait_job(self, job):
        gate(re.fullmatch('[a-f0-9]{32}', job['id']), 'JOB_ID_REQUIRED')
        self.record['jobs'][job['id']] = {'kind': job['kind'], 'initial_status': job['status']}; self.save()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            current = self.api('/jobs/' + job['id'])
            if current['status'] in {'succeeded', 'failed', 'cancelled', 'interrupted'}:
                self.record['jobs'][job['id']].update(status=current['status'], result_sha256=sha(canonical(current.get('result'))))
                self.private_json('job-' + job['id'] + '.json', current)
                self.save(); gate(current['status'] == 'succeeded', 'EXPLICIT_JOB_NOT_SUCCEEDED')
                return current
            time.sleep(.1)
        raise RuntimeError('JOB_WAIT_TIMEOUT_NO_RESUBMISSION')

    def command(self, path, label, body=None):
        key = 'sql-' + self.plan['nonce'] + '-' + label
        completed = self.wait_job(self.api(path, method='POST', body=body, key=key, expected=202))
        duplicate = self.api(path, method='POST', body=body, key=key, expected=202)
        self.check(label + '_confirmed_duplicate_same_job_result', duplicate['id'] == completed['id'] and duplicate['result'] == completed['result'])
        return completed

    def sql_snapshot(self, label):
        tables = {}; definitions = {}
        with self.repo._reading() as connection:
            for name in sorted(self.sql.TABLES):
                table = 'dh_research_' + name
                fields = [row[0] for row in connection.execute('SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) ORDER BY column_id', 'dbo.' + table)]
                gate(fields and all(re.fullmatch('[a-z_][a-z0-9_]*', column) for column in fields), 'SQL_COLUMN_ALLOWLIST_REQUIRED')
                query = 'SELECT ' + ','.join('[' + field + ']' for field in fields) + ' FROM dbo.[' + table + ']'
                parameters = ()
                if 'scope' in fields: query += ' WHERE scope=?'; parameters = (self.profile['installation_id'],)
                rows = [canonical([typed(value) for value in row]) for row in connection.execute(query, *parameters)]
                gate(len(rows) <= 50000, 'SQL_ROW_BOUND_EXCEEDED')
                tables[name] = {'rows': len(rows), 'sha256': sha(b'\n'.join(sorted(rows)))}
            for row in connection.execute("SELECT name,type,OBJECT_DEFINITION(object_id) FROM sys.objects WHERE schema_id=SCHEMA_ID(N'dbo') AND name LIKE N'dh[_]research[_]%' ORDER BY name"):
                definitions[row[0]] = sha(canonical([row[1], row[2]]))
        result = {'tables': tables, 'definitions': definitions}
        self.record.setdefault('sql_snapshots', {})[label] = result
        self.save(); return result

    def database_absent(self):
        connection = self.repo._connect(master=True, autocommit=True)
        try: return connection.execute('SELECT DB_ID(?)', DATABASE).fetchone()[0] is None
        finally: connection.close()

    def typed_projection(self, archive):
        bundle = archive['archive']; archive_id = bundle['archive_id']; scope = self.profile['installation_id']
        with self.repo._reading() as connection:
            columns = {(r[0], r[1]): (r[2], int(r[3]), int(r[4]), int(r[5])) for r in connection.execute("""SELECT t.name,c.name,TYPE_NAME(c.user_type_id),c.max_length,c.precision,c.scale
                FROM sys.tables t JOIN sys.columns c ON c.object_id=t.object_id WHERE t.schema_id=SCHEMA_ID(N'dbo') AND t.name LIKE N'dh[_]research[_]%'""")}
            gate(columns['dh_research_predictions', 'home_probability'][0] == 'decimal'
                and columns['dh_research_predictions', 'home_probability'][2:] == (38, 28), 'EXACT_DECIMAL_SCHEMA_REQUIRED')
            for table, column, typename, size in [('dh_research_archives','payload','nvarchar',-1),
                ('dh_research_archives','payload_sha256','varbinary',32), ('dh_research_archives','input_count','bigint',8),
                ('dh_research_archives','synthetic','bit',1), ('dh_research_notes','note_id','uniqueidentifier',16)]:
                gate(columns[table, column][:2] == (typename, size), 'TYPED_SQL_SCHEMA_REQUIRED')
            for table, column in [('dh_research_predictions','decision_cutoff'), ('dh_research_predictions','predicted_at'), ('dh_research_inputs','usable_at')]:
                gate(columns[table, column][0] == 'datetime2' and columns[table, column][3] == 7, 'UTC_DATETIME2_SCALE_REQUIRED')
            row = connection.execute('SELECT payload,payload_sha256,input_count,synthetic,home_name,away_name FROM dbo.dh_research_archives WHERE scope=? AND archive_id=?', scope, archive_id).fetchone()
            gate(row and row[0].encode('utf-8') == canonical(bundle) and bytes(row[1]) == hashlib.sha256(canonical(bundle)).digest()
                and type(row[2]) is int and row[2] == 50 and row[3] in (False, 0)
                and row[4] == bundle['match']['home']['name'] and row[5] == bundle['match']['away']['name'], 'ARCHIVE_SQL_TYPES_OR_PAYLOAD_MISMATCH')
            original = {p['record_id']: p for p in bundle['predictions']}; seen = set()
            for row in connection.execute("SELECT record_id,model_run_id,home_probability,draw_probability,away_probability,CONVERT(varchar(33),decision_cutoff,126)+'Z',CONVERT(varchar(33),predicted_at,126)+'Z',payload FROM dbo.dh_research_predictions WHERE scope=? AND archive_id=?", scope, archive_id):
                item = original[row[0]]; seen.add(row[0])
                gate(row[1] == item['model_run_id'] and all(isinstance(actual, Decimal) and actual == Decimal(item['probabilities'][key])
                    for actual, key in zip(row[2:5], ('home','draw','away'))), 'EXACT_TYPED_PROBABILITY_ROUNDTRIP_REQUIRED')
                gate(normalize_clock(row[5]) == normalize_clock(item['decision_cutoff']) and normalize_clock(row[6]) == normalize_clock(item['predicted_at'])
                    and canonical(json.loads(row[7])) == canonical(item), 'TYPED_CLOCK_OR_PREDICTION_JSON_MISMATCH')
            gate(seen == set(original) and len(seen) == 5, 'FIVE_TYPED_PREDICTIONS_REQUIRED')
        self.check('actual_sql_typed_projection', True, predictions=5, input_count=50,
            decimal_precision=38, decimal_scale=28, datetime2_scale=7, unicode_note_proof='Verified separately by actual notes',
            unchanged_canonical_payload_sha256=sha(canonical(bundle)))

    def transaction_notes(self):
        scope = self.profile['installation_id']; committed, rolled_back = str(uuid4()), str(uuid4())
        text = 'Direct committed archive note — Québec 🐉'
        at = self.sql._clock()
        statement = 'INSERT INTO dbo.dh_research_notes VALUES(?,?,?,?,1,CONVERT(datetime2(7),?,126),CONVERT(datetime2(7),?,126))'
        with self.repo.transaction() as connection:
            connection.execute(statement, scope, committed, TARGET, text, at, at)
        visible = self.api('/matches/' + TARGET + '/research/notes')['items']
        self.check('actual_adapter_transaction_commits_note_and_audit', any(n['note_id'] == committed and n['text'] == text for n in visible))
        before = self.sql_snapshot('before-forced-rollback')
        failure = None
        try:
            with self.repo.transaction() as connection:
                connection.execute(statement, scope, rolled_back, TARGET, 'Must roll back — 東京', at, at)
                connection.execute('DECLARE @zero int=0; SELECT 1/@zero;').fetchone()
        except self.StorageError as error:
            failure = {'code': error.code, 'sqlstate': error.sqlstate, 'uncertain_write': error.uncertain_write}
        gate(failure is not None and failure['uncertain_write'] is False, 'CONFIRMED_SQL_FAILURE_ROLLBACK_REQUIRED')
        after = self.sql_snapshot('after-forced-rollback')
        self.check('forced_sql_failure_rolls_back_note_and_trigger_audit', before == after, error=failure, rollback_note_id=rolled_back)

    def run(self):
        sys.path.insert(0, str(ROOT / 'src'))
        from dragonhydra.installation_profile import load_binding
        from dragonhydra.build_meta import info
        from dragonhydra.research_storage import sqlserver
        from dragonhydra.research_storage.base import StorageError
        self.sql, self.StorageError = sqlserver, StorageError
        bound, state = load_binding(profile_path=self.plan['profile'])
        gate(bound == self.profile and state == self.state and info()['source_sha'] == self.plan['source_commit'], 'STRICT_SOURCE_PROFILE_BINDING_REQUIRED')
        self.repo = sqlserver.Repo(sqlserver.SQLServerConfig.from_dict(self.settings['sqlserver']), self.profile['installation_id'])
        for port in self.profile['ports'].values():
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind(('127.0.0.1', port))
        self.check('exact_new_profile_source_private_python_and_sql_database_absent', self.database_absent(),
            profile_sha256=digest(self.plan['profile']), implementation_plan_sha256=digest(self.plan_path))
        self.launch()
        initial = self.snapshot('01-after-start-before-passive')
        self.check('canonical_fixture_reads_while_secondary_uninitialized', self.api('/matches?limit=1')['total'] == 760
            and self.api('/research/storage')['research']['ready'] is False and self.database_absent())
        engines, inventory = self.api('/modules'), self.api('/modules?scope=all')
        self.check('authenticated_registry_six_engines_eighteen_modules', len(engines['items']) == 6 and len(inventory['items']) == 18)
        gate(initial == self.snapshot('02-after-initial-passive'), 'PASSIVE_READ_CHANGED_SQLITE')
        initialization = self.command('/research/storage/initialize', 'initialize-a')
        self.check('app_job_created_owned_secondary_sql_database', initialization['result']['created_database'] is True and self.api('/research/storage')['research']['ready'] is True)
        empty = self.sql_snapshot('03-initialized-empty')
        self.check('owned_eight_tables_nine_enabled_triggers_empty_projection', len(empty['tables']) == 8
            and all(empty['tables'][name]['rows'] == 0 for name in ('archives','models','predictions','inputs','notes','note_audit')))
        forecast = self.command('/matches/' + TARGET + '/forecasts', 'forecast')
        result = forecast['result']; models, predictions = result['model_runs'], result['predictions']
        self.check('existing_four_models_and_ensemble_fifty_original_inputs', result['status'] == 'persisted'
            and len(models) == len(predictions) == 5 and {m['model_name'] for m in models} == MODEL_NAMES
            and all(len(m['training_manifest']) == 50 for m in models))
        self.check('forecast_does_not_automatically_publish_to_sql', self.sql_snapshot('04-after-canonical-forecast') == empty)
        before_publication = self.snapshot('03-after-canonical-forecast')
        published = self.command('/matches/' + TARGET + '/research/archives', 'archive', {'forecast_run_id': forecast['id']})
        archive_id = published['result']['archive_id']
        gate(re.fullmatch('[a-f0-9]{64}', archive_id), 'SQL_ARCHIVE_ID_REQUIRED')
        archive = self.api('/research/archives/' + archive_id)
        if 'installation' in archive: gate(archive['installation']['installation_id'] == self.profile['installation_id'], 'SQL_API_PROFILE_BINDING_REQUIRED')
        data = archive['archive']
        self.check('sql_api_archive_preserves_original_models_predictions_and_inputs', canonical(data['models']) == canonical(models)
            and canonical(data['predictions']) == canonical(predictions) and canonical(data['input_manifest']) == canonical(models[0]['training_manifest'])
            and data['forecast_run_id'] == forecast['id'] and data['source_build']['source_sha'] == self.plan['source_commit'])
        self.record['archive_id'] = archive_id
        self.record['canonical_forecast'] = self.private_json('canonical-forecast.json', result)
        self.record['sql_archive'] = self.private_json('sql-archive.json', archive)
        self.typed_projection(archive)
        read_match = self.api('/research/archives/' + archive_id + '/match')
        history = self.api('/matches/' + TARGET + '/research/archives')['items']
        self.check('data_engine_reads_sql_match_and_scoped_history', read_match['match'] == data['match'] and len(history) == 1 and history[0]['archive']['archive_id'] == archive_id)
        foreign = sqlserver.Repo(self.repo.config, 'foreign-' + self.plan['nonce'])
        self.check('foreign_scope_cannot_read_archives_or_notes', foreign.get(archive_id) is None and foreign.history(TARGET) == [] and foreign.notes(TARGET) == [])
        after_publication = self.snapshot('04-after-explicit-publication')
        self.check('publication_preserves_canonical_memory_source_and_provider_rows', source_protection(before_publication, after_publication, include_memory=True))
        before_repeat = self.sql_snapshot('05-before-second-initializer')
        second = self.command('/research/storage/initialize', 'initialize-b')
        self.check('second_real_initializer_preserves_all_sql_rows_and_ddl', second['result']['created_database'] is False and before_repeat == self.sql_snapshot('06-after-second-initializer'))
        text = 'Research note — Québec 東京 🐉'
        note = self.api('/research/notes', method='POST', body={'match_id': TARGET, 'text': text})
        gate(note['text'] == text and note['revision'] == 1, 'UNICODE_NOTE_CREATE_FAILED')
        updated_text = text + ' / revised'
        updated = self.api('/research/notes/' + note['note_id'], method='PUT', body={'text': updated_text, 'expected_revision': 1})
        gate(updated['text'] == updated_text and updated['revision'] == 2, 'UNICODE_NOTE_UPDATE_FAILED')
        before_stale = self.sql_snapshot('07-before-stale-note-update')
        stale = self.api('/research/notes/' + note['note_id'], method='PUT', body={'text': 'Must not replace current note', 'expected_revision': 1}, expected=409)
        self.check('unicode_notes_and_stale_revision_409', stale['error']['code'] == 'SQLSERVER_NOTE_REVISION_CONFLICT'
            and before_stale == self.sql_snapshot('08-after-stale-note-update'))
        self.transaction_notes()
        sql_before_reads = self.sql_snapshot('09-before-passive-sql-reads')
        sqlite_before_reads = self.snapshot('05-before-final-passive')
        for path in ['/research/storage', '/research/archives/' + archive_id, '/research/archives/' + archive_id + '/match',
                     '/matches/' + TARGET + '/research/archives', '/matches/' + TARGET + '/research/notes', '/modules', '/modules?scope=all']:
            self.api(path)
        self.api('/research/archives/' + archive_id, anonymous=True, expected=401)
        self.api('/research/storage/initialize', method='POST', anonymous=True, expected=401)
        self.check('passive_api_reads_and_anonymous_denials_do_not_write', sql_before_reads == self.sql_snapshot('10-after-passive-sql-reads')
            and sqlite_before_reads == self.snapshot('06-after-final-passive'))
        final_sql = self.sql_snapshot('11-before-restart')
        expected_counts = {'owner': 1, 'migrations': 1, 'archives': 1, 'models': 5, 'predictions': 5, 'inputs': 50, 'notes': 2, 'note_audit': 3}
        self.check('actual_projection_and_note_audit_counts', {k: v['rows'] for k, v in final_sql['tables'].items()} == expected_counts)
        gate(source_protection(initial, sqlite_before_reads), 'CANONICAL_SOURCE_OR_PROVIDER_ROWS_CHANGED')
        pairing_hash, settings_hash = digest(self.state / 'local-session.json'), digest(self.state / 'research-storage.json')
        self.stop(); self.launch()
        reopened = self.api('/research/archives/' + archive_id)
        self.check('restart_preserves_sql_archive_all_record_ids_notes_jobs_and_pairing', reopened == archive
            and final_sql == self.sql_snapshot('12-after-restart')
            and digest(self.state / 'local-session.json') == pairing_hash and digest(self.state / 'research-storage.json') == settings_hash
            and all(self.api('/jobs/' + identifier)['status'] == 'succeeded' for identifier in self.record['jobs']))
        final_sqlite = self.snapshot('07-after-restart')
        self.check('restart_and_sql_publication_keep_canonical_retained_760', source_protection(initial, final_sqlite)
            and source_protection(after_publication, final_sqlite, include_memory=True))
        self.stop()
        self.check('both_owned_app_lifetimes_shutdown_cleanly', len(self.record['lifetimes']) == 2
            and all(item['exit_code'] == 0 and item['port_free'] for item in self.record['lifetimes']))
        self.record.update(passed=True, status='PASS', finished_at=now(), database_retained=True,
            direct_sql_schema_types_verified=True, no_predictive_accuracy_claim=True,
            numeric_comparison='Separate frozen795/cohort analysis; not inferred by this SQL persistence acceptance')
        self.save()


class OperationGuardTests(TestCase):
    """Pure transport double: no files, app, ODBC or actual HTTP requests."""

    def candidate(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return b'{"fixture":true}'
        class Transport:
            def __init__(self): self.requests = []
            def open(self, request, timeout):
                self.requests.append((request.full_url, timeout))
                return Response()
        candidate = object.__new__(Acceptance)
        candidate.plan = {'target_match': TARGET}
        candidate.origin = 'http://127.0.0.1:9'
        candidate.token = 'synthetic-unit-credential'
        candidate.opener = Transport()
        candidate.record = {'requests': []}
        candidate.save = lambda: None
        return candidate

    def test_dynamic_read_routes_are_boolean_and_reach_only_fake_transport(self):
        for path in ['/jobs/' + '1' * 32, '/research/archives/' + '2' * 64,
                     '/research/archives/' + '2' * 64 + '/match']:
            with self.subTest(path_kind=path.split('/')[1]):
                candidate = self.candidate()
                self.assertEqual(candidate.api(path), {'fixture': True})
                self.assertEqual(len(candidate.opener.requests), 1)
                self.assertEqual(candidate.record['requests'][0]['status'], 200)

    def test_unrelated_path_is_rejected_before_transport(self):
        candidate = self.candidate()
        with self.assertRaisesRegex(RuntimeError, 'NARROW_API_OPERATION_REQUIRED'):
            candidate.api('/unrelated/path')
        self.assertEqual(candidate.opener.requests, [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-plan-sha256')
    args = parser.parse_args()
    try:
        values = validate_plan(args)
        plan_path, plan, profile, state, output, settings = values
        if not args.apply:
            print(json.dumps({'status': 'PREVIEW_NOT_EXECUTED', 'source_commit': plan['source_commit'],
                'installation_id': profile['installation_id'], 'database': DATABASE, 'plan_sha256': digest(plan_path), 'mutations': False}))
            return 0
        gate(args.expected_plan_sha256 == digest(plan_path), 'REVIEWED_PLAN_HASH_REQUIRED')
        output.mkdir(); (output / 'private').mkdir()
        with (output / 'APPLY.started.lock').open('xb') as marker: marker.write(canonical({'started_at': now(), 'plan_sha256': digest(plan_path)}))
        run = Acceptance(*values)
        try:
            run.run()
        except BaseException as error:
            code = str(error) if re.fullmatch('[A-Z0-9_]{1,128}', str(error)) else 'SANITIZED_ACCEPTANCE_FAILURE'
            run.record.update(passed=False, status='FAIL', failure_code=code, failure_class=type(error).__name__, finished_at=now())
            if run.process is not None and run.process.poll() is None:
                try: run.stop()
                except BaseException as cleanup:
                    run.record['cleanup_failure_class'] = type(cleanup).__name__
                    run.record['owned_process_left_for_coordinator'] = run.process.pid
            run.save()
        finally:
            for stream in run.streams: stream.close()
        print(json.dumps({'passed': run.record['passed'], 'receipt': str(output / 'verification.json'),
            'receipt_sha256': digest(output / 'verification.json'), 'failure_code': run.record.get('failure_code')}))
        return 0 if run.record['passed'] else 1
    except Exception as error:
        code = str(error) if re.fullmatch('[A-Z0-9_]{1,128}', str(error)) else 'SANITIZED_PREFLIGHT_FAILURE'
        print(json.dumps({'passed': False, 'stage': 'preflight', 'failure_code': code, 'failure_class': type(error).__name__, 'runtime_started': False}))
        return 1


if __name__ == '__main__': raise SystemExit(main())
