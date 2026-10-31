"""Private, verifiable SQLite migration preparation; no backend switch or SQL writer.

An online backup freezes committed SQLite state, including WAL contents. Typed
exports and source evidence accompany that backup. Integrity hashes detect drift;
they are not signatures or encryption. Session hashes and queued payloads make
the entire bundle private, even though no vault or sibling credentials are copied.
"""
from __future__ import annotations

import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import time

from .server import protect


ROOT = Path(__file__).resolve().parents[2]
VERSION = 'dragonhydra-sqlite-preparation/1'
CONTEXT_VERSION = 'dragonhydra-sqlite-preparation/2'
STATUS = 'migration_preparation_only'
CORE_PROFILE = 'core-1'
CONTEXT_PROFILE = 'core-context-1'
CONTEXT_TABLES = frozenset({'cognitive_records', 'cognitive_receipts'})
CORE_TABLES = frozenset({
    'raw_sources', 'public_result_captures', 'public_result_receipts',
    'public_fixture_records', 'public_fixture_quarantine',
    'connector_acquisitions', 'connector_observations', 'connector_quarantine',
    'connector_identity_review', 'connector_attempts', 'connector_settings',
    'product_schema', 'product_jobs', 'product_updates', 'product_sessions',
    'product_bridge_nonces',
})


class MigrationError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _fail(code, message):
    raise MigrationError(code, message)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _local(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ROOT) or resolved == ROOT:
        _fail('PATH_OUTSIDE_WORKSPACE', 'Choose an explicit path inside the DRAGONHYDRA workspace.')
    return resolved


def _private(path):
    # server.protect deliberately uses file mode 0600 on POSIX. Directories
    # need owner traversal as well; Windows uses the existing ACL protection.
    if os.name != 'nt' and path.is_dir():
        path.chmod(0o700)
    else:
        protect(path)


def _directory(path):
    path.mkdir()
    _private(path)


def _open_private(path):
    output = path.open('xb')
    try:
        _private(path)
    except Exception:
        output.close()
        raise
    return output


def _write(path, value):
    with _open_private(path) as output:
        output.write(canonical(value)+b'\n')
        output.flush()
        os.fsync(output.fileno())


def _digest_file(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(256*1024), b''):
            digest.update(part)
            size += len(part)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def _read_only(path):
    # Never use immutable=1: that would ignore a live source's committed WAL.
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5, isolation_level=None)
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA trusted_schema=OFF')
    return db


def _integrity(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        _fail('SQLITE_INTEGRITY_FAILED', 'The SQLite snapshot failed its integrity check.')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        _fail('SQLITE_FOREIGN_KEY_FAILED', 'The SQLite snapshot contains broken foreign-key references.')


def _schema(db):
    objects = [{'type': kind, 'name': name, 'table': table, 'sql': sql}
               for kind, name, table, sql in db.execute(
                   'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
    tables = {item['name'] for item in objects if item['type'] == 'table'}
    if not tables or tables-CORE_TABLES-CONTEXT_TABLES-{'sqlite_sequence'}:
        _fail('UNSUPPORTED_TABLE', 'This preparation supports only the known DRAGONHYDRA core tables.')
    extensions = tables & CONTEXT_TABLES
    if extensions:
        if extensions != CONTEXT_TABLES:
            _fail('UNSUPPORTED_SCHEMA_PROFILE', 'The context profile requires both exact cognitive tables and their immutable triggers.')
        # The reviewed core DDL already lives with the strict offline writer.
        # Import lazily to preserve the legacy preparation path and reuse that
        # exact signature rather than maintaining a second schema allowlist.
        from . import mariadb_migration
        try:
            mariadb_migration._verify_schema(db, CONTEXT_PROFILE)
        except mariadb_migration.MariaDBMigrationError:
            _fail('UNSUPPORTED_SCHEMA_PROFILE', 'The context profile does not match the exact audited eighteen-table schema.')
    for item in objects:
        if item['type'] not in ('table', 'index', 'trigger') or item['table'] not in tables:
            _fail('UNSUPPORTED_SCHEMA', 'Views and unrecognized schema objects require an explicit migration design.')
        if item['type'] == 'table' and re.match(r'\s*CREATE\s+VIRTUAL\s+TABLE\b', item['sql'] or '', re.IGNORECASE):
            _fail('UNSUPPORTED_SCHEMA', 'Virtual tables are not supported by this migration preparation.')
    return objects


def schema_profile(objects):
    return CONTEXT_PROFILE if any(item['type'] == 'table' and item['name'] in CONTEXT_TABLES
                                  for item in objects) else CORE_PROFILE


def bundle_profile(manifest):
    """Dispatch known preparation versions; a v2 context declaration is mandatory."""
    version = manifest.get('bundle_version')
    profile = manifest.get('schema_profile', CORE_PROFILE)
    if ((version == VERSION and profile == CORE_PROFILE)
            or (version == CONTEXT_VERSION and profile == CONTEXT_PROFILE)):
        return profile
    _fail('BUNDLE_VERSION_UNSUPPORTED', 'This is not a supported versioned migration schema profile.')


def _quote(value):
    return '"'+value.replace('"', '""')+'"'


def _tables(db):
    result = []
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence' ORDER BY name"):
        columns = [{'cid': cid, 'name': column, 'declared_type': kind, 'not_null': bool(required),
                    'default_sql': default, 'primary_key_position': primary}
                   for cid, column, kind, required, default, primary, hidden in db.execute('PRAGMA table_xinfo('+_quote(name)+')')
                   if not hidden]
        count = db.execute('PRAGMA table_xinfo('+_quote(name)+')').fetchall()
        keys = [item['name'] for item in sorted(columns, key=lambda item: item['primary_key_position']) if item['primary_key_position']]
        if len(columns) != len(count) or not keys:
            _fail('UNSUPPORTED_SCHEMA', 'Every exported table needs ordinary columns and an explicit primary key.')
        if db.execute('SELECT 1 FROM '+_quote(name)+' WHERE '+' OR '.join(_quote(key)+' IS NULL' for key in keys)+' LIMIT 1').fetchone():
            _fail('NULL_PRIMARY_KEY', 'A primary-key value is NULL; deterministic migration ordering needs review.')
        result.append({'name': name, 'columns': columns, 'primary_key': keys, 'path': 'tables/'+name+'.jsonl'})
    return result


def _sequences(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone()
    values = [list(row) for row in db.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name')] if exists else []
    for name, high_water in values:
        if name not in CORE_TABLES or type(high_water) is not int or high_water < 0:
            _fail('UNSUPPORTED_SEQUENCE', 'A SQLite sequence entry requires explicit migration review.')
    return values


def typed_cell(value):
    """Preserve SQLite storage types without JSON integer/float precision loss."""
    if value is None:
        return ['null']
    if type(value) is int:
        return ['int', str(value)]
    if type(value) is float:
        return ['float', value.hex()]
    if isinstance(value, str):
        return ['text', value]
    if isinstance(value, bytes):
        return ['blob', base64.b64encode(value).decode('ascii')]
    _fail('UNSUPPORTED_VALUE', 'A SQLite value has an unsupported storage type.')


def _table_rows(db, table, output=None, verify=None):
    query = 'SELECT '+','.join(_quote(item['name']) for item in table['columns'])+' FROM '+_quote(table['name'])
    query += ' ORDER BY '+','.join(_quote(key) for key in table['primary_key'])
    rows_hash, file_hash, row_count, size = hashlib.sha256(), hashlib.sha256(), 0, 0
    for row in db.execute(query):
        cells = [typed_cell(value) for value in row]
        row_hash = hashlib.sha256(canonical(cells)).hexdigest()
        line = canonical({'values': cells, 'row_sha256': row_hash})+b'\n'
        if output is not None:
            output.write(line)
        if verify is not None and verify.readline() != line:
            _fail('TABLE_EXPORT_MISMATCH', 'A typed row export does not match the retained SQLite snapshot.')
        rows_hash.update(bytes.fromhex(row_hash))
        file_hash.update(line)
        row_count += 1
        size += len(line)
    if verify is not None and verify.read(1):
        _fail('TABLE_EXPORT_MISMATCH', 'A typed row export contains unexpected trailing rows.')
    return {**table, 'row_count': row_count, 'rows_sha256': rows_hash.hexdigest(),
            'bytes': size, 'sha256': file_hash.hexdigest()}


def _references(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connector_acquisitions'").fetchone():
        return []
    refs = {}
    try:
        cursor = db.execute('SELECT id,sha256,raw_reference,bytes FROM connector_acquisitions ORDER BY id')
        for ident, digest, filename, size in cursor:
            if (not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)
                    or filename != digest+'.payload' or type(size) is not int or size < 0):
                _fail('RAW_REFERENCE_INVALID', 'A connector acquisition has an unsafe or invalid raw evidence reference.')
            previous = refs.setdefault(filename, {'path': 'raw/connectors/'+filename, 'sha256': digest,
                                                   'bytes': size, 'acquisition_ids': []})
            if previous['bytes'] != size:
                _fail('RAW_REFERENCE_INVALID', 'Acquisitions disagree on the retained payload length.')
            previous['acquisition_ids'].append(ident)
    except sqlite3.Error:
        _fail('UNSUPPORTED_SCHEMA', 'Connector acquisitions do not have the supported evidence-reference columns.')
    return [refs[key] for key in sorted(refs)]


def _artifact(bundle, relative):
    path = PurePosixPath(relative)
    if (path.is_absolute() or not path.parts or any(part in ('.', '..') or not re.fullmatch('[A-Za-z0-9_.-]+', part) for part in path.parts)):
        _fail('BUNDLE_PATH_INVALID', 'A bundle artifact path is unsafe.')
    target = bundle.joinpath(*path.parts)
    if not target.resolve().is_relative_to(bundle) or target.is_symlink():
        _fail('BUNDLE_PATH_INVALID', 'A bundle artifact must remain inside its owned directory.')
    return target


def _copy_raw(source, bundle, references):
    raw = source.parent/'raw'/'connectors'
    if references and (not raw.resolve().is_relative_to(source.parent) or not raw.resolve().is_relative_to(ROOT)):
        _fail('RAW_REFERENCE_INVALID', 'The source raw evidence directory resolves outside the selected state.')
    for item in references:
        filename = PurePosixPath(item['path']).name
        original = raw/filename
        if original.is_symlink() or original.resolve().parent != raw.resolve():
            _fail('RAW_REFERENCE_INVALID', 'A source payload must be a contained ordinary file.')
        if not original.is_file():
            _fail('RAW_EVIDENCE_MISSING', 'A referenced connector payload is absent; no complete migration bundle was produced.')
        destination = _artifact(bundle, item['path'])
        digest, size = hashlib.sha256(), 0
        with original.open('rb') as incoming, _open_private(destination) as outgoing:
            for part in iter(lambda: incoming.read(256*1024), b''):
                digest.update(part)
                size += len(part)
                outgoing.write(part)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if digest.hexdigest() != item['sha256'] or size != item['bytes']:
            _fail('RAW_EVIDENCE_CORRUPT', 'A referenced connector payload failed its retained hash or length check.')


def prepare(source, output):
    """Create an exclusive private bundle; never alter database authority or jobs."""
    source, output = _local(source), _local(output)
    if source.name != 'core.sqlite3' or not source.is_file():
        _fail('SOURCE_DATABASE_REQUIRED', 'Select an existing project-local core.sqlite3 explicitly.')
    if output.exists():
        _fail('OUTPUT_EXISTS', 'Choose a new bundle directory; existing results are never overwritten.')
    if output.is_relative_to(source.parent):
        _fail('OUTPUT_INSIDE_SOURCE_STATE', 'Keep the migration bundle outside the selected live state directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    _directory(output)
    started = _now()
    snapshot = output/'core.sqlite3'
    try:
        with _open_private(snapshot):
            pass
        with closing(_read_only(source)) as incoming, closing(sqlite3.connect(snapshot)) as target:
            incoming.execute('BEGIN')
            try:
                # Establish the read snapshot before backup. Other writers may
                # continue; their later commits cannot change this transaction.
                source_schema = incoming.execute('PRAGMA schema_version').fetchone()[0]
                source_journal = incoming.execute('PRAGMA journal_mode').fetchone()[0]
                source_data_version = incoming.execute('PRAGMA data_version').fetchone()[0]
                deadline = time.monotonic()+60

                def bounded(status, remaining, total):
                    if time.monotonic() > deadline:
                        _fail('SNAPSHOT_TIMEOUT', 'The online snapshot exceeded its bounded preparation time.')

                incoming.backup(target, pages=256, progress=bounded, sleep=.05)
            finally:
                incoming.rollback()
            target.commit()
            # A closed, standalone rollback-journal snapshot avoids depending
            # on a destination WAL sidecar. This changes only our owned copy.
            target.execute('PRAGMA journal_mode=DELETE')
        _directory(output/'tables')
        _directory(output/'raw')
        _directory(output/'raw'/'connectors')
        with closing(_read_only(snapshot)) as db:
            _integrity(db)
            schema = _schema(db)
            profile = schema_profile(schema)
            references = _references(db)
            _copy_raw(source, output, references)
            _write(output/'schema.json', schema)
            tables = []
            for table in _tables(db):
                with _open_private(_artifact(output, table['path'])) as destination:
                    tables.append(_table_rows(db, table, output=destination))
                    destination.flush()
                    os.fsync(destination.fileno())
            manifest = {
                'bundle_version': CONTEXT_VERSION if profile == CONTEXT_PROFILE else VERSION, 'status': STATUS,
                'started_at': started, 'finished_at': _now(),
                'source': {'path': source.relative_to(ROOT).as_posix(), 'access': 'mode=ro; query_only=ON',
                           'transaction': 'BEGIN; online backup; ROLLBACK', 'schema_version': source_schema,
                           'data_version': source_data_version, 'journal_mode': source_journal,
                           'concurrent_writer_changes': 'Possible; the backup preserves one committed read snapshot.'},
                'snapshot': {'path': 'core.sqlite3', **_digest_file(snapshot),
                             'user_version': db.execute('PRAGMA user_version').fetchone()[0],
                             'application_id': db.execute('PRAGMA application_id').fetchone()[0],
                             'encoding': db.execute('PRAGMA encoding').fetchone()[0]},
                'schema': {'path': 'schema.json', **_digest_file(output/'schema.json')},
                'tables': tables, 'sequences': _sequences(db), 'raw_payloads': references,
                'checks': {'integrity_check': 'ok', 'foreign_key_check': 'ok'},
                'privacy': {'classification': 'private database backup and exports; contains session hashes and queued payloads',
                            'vault_or_sibling_credential_files_copied': False,
                            'protection': 'Owner and SYSTEM ACL on Windows; owner-only files/directories on POSIX',
                            'hashes_are_authentication': False},
                'limits': ['No MariaDB SQL writer, database authority switch, credential export or service restart.',
                           'The typed exports are a migration foundation, not a verified MariaDB restore.'],
                'sqlite_runtime_version': sqlite3.sqlite_version,
            }
            if profile == CONTEXT_PROFILE:
                manifest['schema_profile'] = profile
        manifest['manifest_sha256'] = hashlib.sha256(canonical(manifest)).hexdigest()
        _write(output/'manifest.json', manifest)
        verification = validate_bundle(output)
        _write(output/'verification.json', verification)
        return verification
    except Exception as error:
        # Leave protected evidence for diagnosis. A failed candidate cannot pass
        # verification and is never reused or treated as a completed migration.
        failure = {'status': 'preparation_failed', 'at': _now(),
                   'code': error.code if isinstance(error, MigrationError) else type(error).__name__,
                   'message': error.message if isinstance(error, MigrationError) else 'Migration preparation failed; source access was read-only.'}
        if not (output/'failure.json').exists():
            _write(output/'failure.json', failure)
        raise


def validate_bundle(bundle):
    """Reopen the snapshot and recompute schema, typed rows, sequences and raw hashes."""
    bundle = _local(bundle)
    try:
        manifest_path = _artifact(bundle, 'manifest.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        profile = bundle_profile(manifest)
        if manifest['status'] != STATUS:
            _fail('BUNDLE_VERSION_UNSUPPORTED', 'This is not a supported migration preparation bundle.')
        declared = manifest['manifest_sha256']
        if hashlib.sha256(canonical({key: value for key, value in manifest.items() if key != 'manifest_sha256'})).hexdigest() != declared:
            _fail('MANIFEST_HASH_MISMATCH', 'The migration manifest changed after preparation.')
        expected_files = {'manifest.json', 'verification.json'}
        for item in [manifest['snapshot'], manifest['schema'], *manifest['tables'], *manifest['raw_payloads']]:
            path = _artifact(bundle, item['path'])
            expected_files.add(item['path'])
            if not path.is_file() or _digest_file(path) != {key: item[key] for key in ('bytes', 'sha256')}:
                _fail('ARTIFACT_HASH_MISMATCH', 'A required migration artifact is absent or changed.')
        expected_dirs = {'tables', 'raw', 'raw/connectors'}
        for path in bundle.rglob('*'):
            relative = path.relative_to(bundle).as_posix()
            if path.is_symlink() or (path.is_dir() and relative not in expected_dirs) or (path.is_file() and relative not in expected_files):
                _fail('UNEXPECTED_BUNDLE_ARTIFACT', 'The private bundle contains an unexpected or linked artifact.')
        snapshot = _artifact(bundle, manifest['snapshot']['path'])
        if snapshot.name != 'core.sqlite3':
            _fail('BUNDLE_PATH_INVALID', 'The retained SQLite snapshot has an unexpected name.')
        with closing(_read_only(snapshot)) as db:
            _integrity(db)
            schema = _schema(db)
            if schema_profile(schema) != profile:
                _fail('BUNDLE_PROFILE_MISMATCH', 'The declared migration profile differs from its retained schema.')
            if canonical(schema)+b'\n' != _artifact(bundle, manifest['schema']['path']).read_bytes():
                _fail('SCHEMA_EXPORT_MISMATCH', 'Schema definitions differ from the retained snapshot.')
            if manifest['sequences'] != _sequences(db):
                _fail('SEQUENCE_MISMATCH', 'SQLite sequence high-water marks differ from the retained snapshot.')
            if manifest['raw_payloads'] != _references(db):
                _fail('RAW_REFERENCE_MISMATCH', 'Raw evidence references differ from the retained snapshot.')
            tables = []
            for table in _tables(db):
                with _artifact(bundle, table['path']).open('rb') as exported:
                    tables.append(_table_rows(db, table, verify=exported))
            if tables != manifest['tables']:
                _fail('TABLE_EXPORT_MISMATCH', 'Table counts, schemas or hashes differ from the retained snapshot.')
            for key in ('user_version', 'application_id', 'encoding'):
                if db.execute('PRAGMA '+key).fetchone()[0] != manifest['snapshot'][key]:
                    _fail('SNAPSHOT_METADATA_MISMATCH', 'SQLite metadata differs from the declared snapshot.')
        result = {'valid': True, 'status': STATUS, 'bundle': bundle.relative_to(ROOT).as_posix(),
                'manifest_sha256': declared, 'snapshot_sha256': manifest['snapshot']['sha256'],
                'table_count': len(tables), 'row_count': sum(item['row_count'] for item in tables),
                'raw_payload_count': len(manifest['raw_payloads']),
                'raw_payload_bytes': sum(item['bytes'] for item in manifest['raw_payloads']),
                'integrity_check': 'ok', 'foreign_key_check': 'ok',
                'verified_at': _now(), 'source_access': 'read_only', 'backend_changed': False}
        if profile == CONTEXT_PROFILE:
            result['schema_profile'] = profile
        return result
    except MigrationError:
        raise
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        _fail('BUNDLE_INVALID', 'The migration bundle is incomplete or malformed; no restore was attempted.')
