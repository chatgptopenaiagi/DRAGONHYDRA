"""Offline, strict MariaDB staging SQL from a verified private SQLite bundle.

This module never connects to MariaDB, reads credentials or changes authority.
Its audited v1 mapping accepts the sixteen-table core schema; v2 accepts the
exact core plus two existing cognitive tables and four immutable triggers.
Every text value is hex-encoded; identity keys use complete UTF-8 VARBINARY
values so case and trailing spaces remain significant. Runtime compatibility
and a future application backend adapter require separate verification.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from . import migration


VERSION = 'dragonhydra-mariadb-staging/1'
CONTEXT_VERSION = 'dragonhydra-mariadb-staging/2'
STATUS = 'mariadb_staging_script_only'
MAX_KEY_BYTES = 3072
MAX_BIGINT = 9223372036854775807
SQL_MODE = 'STRICT_ALL_TABLES,NO_AUTO_VALUE_ON_ZERO,NO_BACKSLASH_ESCAPES,ERROR_FOR_DIVISION_BY_ZERO'
DOCUMENTATION = [
    'https://mariadb.com/docs/server/reference/data-types/string-data-types/varbinary',
    'https://mariadb.com/docs/server/server-usage/storage-engines/innodb/innodb-limitations',
    'https://mariadb.com/docs/server/ha-and-performance/optimization-and-tuning/optimization-and-indexes/foreign-keys',
    'https://mariadb.com/docs/server/reference/data-types/null-values',
    'https://mariadb.com/docs/server/server-usage/tables/create-table',
    'https://mariadb.com/docs/server/reference/sql-statements/programmatic-compound-statements/signal',
    'https://mariadb.com/docs/server/reference/sql-functions/string-functions/convert',
]

# These are reviewed definitions, never SQL supplied by a bundle or user. A
# private in-memory SQLite database provides the matching reference metadata.
# Unknown columns, constraints, indexes, triggers and declarations fail closed.
SOURCE_DDL = '''
CREATE TABLE raw_sources (source_hash TEXT PRIMARY KEY, bytes BLOB NOT NULL);
CREATE TABLE public_result_captures (
 source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL,
 source_hash TEXT NOT NULL REFERENCES raw_sources(source_hash), source_url TEXT NOT NULL,
 received_at TEXT NOT NULL, source_capture_at TEXT, receipt_json TEXT,
 PRIMARY KEY(source_id, acquisition_id));
CREATE TABLE public_result_receipts (
 source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, persisted_at TEXT NOT NULL, usable_at TEXT NOT NULL,
 PRIMARY KEY(source_id, acquisition_id),
 FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
CREATE TABLE public_fixture_records (
 source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
 fixture_key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source_id,acquisition_id,ordinal),
 FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
CREATE TABLE public_fixture_quarantine (
 source_id TEXT NOT NULL, acquisition_id TEXT NOT NULL, ordinal INTEGER NOT NULL, reason TEXT NOT NULL,
 PRIMARY KEY(source_id,acquisition_id,ordinal),
 FOREIGN KEY(source_id,acquisition_id) REFERENCES public_result_captures(source_id,acquisition_id));
CREATE TABLE connector_acquisitions (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, adapter_version TEXT NOT NULL,
 original_url TEXT NOT NULL, resolved_url TEXT NOT NULL, captured_at TEXT NOT NULL,
 sha256 TEXT NOT NULL, raw_reference TEXT NOT NULL, bytes INTEGER NOT NULL,
 content_type TEXT NOT NULL, http_status INTEGER NOT NULL);
CREATE TABLE connector_observations (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 provider TEXT NOT NULL, source_record_id TEXT NOT NULL, sport TEXT NOT NULL,
 event_date TEXT NOT NULL, status TEXT NOT NULL, content_hash TEXT NOT NULL,
 acquisition_id TEXT NOT NULL REFERENCES connector_acquisitions(id),
 received_at TEXT NOT NULL, usable_at TEXT NOT NULL, record TEXT NOT NULL);
CREATE INDEX connector_latest ON connector_observations(provider,source_record_id,seq DESC);
CREATE INDEX connector_events ON connector_observations(sport,event_date,status);
CREATE TABLE connector_quarantine (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, source_record_id TEXT,
 reason TEXT NOT NULL, acquisition_id TEXT, record TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE connector_identity_review (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, source_record_id TEXT NOT NULL,
 other_provider TEXT NOT NULL, other_record_id TEXT NOT NULL, reason TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'review_required', created_at TEXT NOT NULL);
CREATE TABLE connector_attempts (
 id TEXT PRIMARY KEY, job_id TEXT, provider TEXT NOT NULL, operation TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, result TEXT, error TEXT);
CREATE INDEX connector_attempt_provider ON connector_attempts(provider,started_at DESC);
CREATE TABLE connector_settings (
 provider TEXT PRIMARY KEY, config TEXT NOT NULL DEFAULT '{}',
 interval_seconds INTEGER NOT NULL DEFAULT 0, next_due REAL NOT NULL DEFAULT 0);
CREATE TABLE product_schema (version INTEGER PRIMARY KEY);
CREATE TABLE product_jobs (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
 idempotency_key TEXT, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 heartbeat REAL, lease_until REAL, deadline REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
 result TEXT, error TEXT, next_attempt REAL NOT NULL DEFAULT 0, UNIQUE(owner,idempotency_key));
CREATE TABLE product_updates (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL, committed_at TEXT NOT NULL);
CREATE TABLE product_sessions (
 token_hash TEXT PRIMARY KEY, user TEXT NOT NULL, roles TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE product_bridge_nonces (nonce TEXT PRIMARY KEY, expires REAL NOT NULL);
'''
IMMUTABLE_TABLES = {
    'raw_sources': 'public_raw', 'public_result_captures': 'public_capture',
    'public_result_receipts': 'public_receipt', 'public_fixture_records': 'public_fixture',
    'public_fixture_quarantine': 'public_quarantine',
}

# Byte capacities, independent of observed data. All indexed/FK/PK TEXT must
# appear here. Composite budgets include full keys and conservatively account
# for the primary-key suffix of secondary InnoDB records. No prefix indexes.
TEXT_CAPACITIES = {
    'raw_sources': {'source_hash': 64},
    'public_result_captures': {'source_id': 255, 'acquisition_id': 128, 'source_hash': 64},
    'public_result_receipts': {'source_id': 255, 'acquisition_id': 128},
    'public_fixture_records': {'source_id': 255, 'acquisition_id': 128},
    'public_fixture_quarantine': {'source_id': 255, 'acquisition_id': 128},
    'connector_acquisitions': {'id': 128},
    'connector_observations': {'id': 128, 'provider': 128, 'source_record_id': 512,
                              'sport': 64, 'event_date': 32, 'status': 64, 'acquisition_id': 128},
    'connector_quarantine': {'id': 128}, 'connector_identity_review': {'id': 128},
    'connector_attempts': {'id': 128, 'provider': 128, 'started_at': 64},
    'connector_settings': {'provider': 128}, 'product_bridge_nonces': {'nonce': 256},
    'product_jobs': {'id': 128, 'owner': 512, 'idempotency_key': 512},
    'product_sessions': {'token_hash': 128},
}
CONTEXT_TEXT_CAPACITIES = {
    'cognitive_records': {'kind': 64, 'record_id': 128, 'natural_key': 64},
    'cognitive_receipts': {'record_id': 128},
}


class MariaDBMigrationError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _fail(code, message):
    raise MariaDBMigrationError(code, message)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _identifier(name):
    if not isinstance(name, str) or not re.fullmatch('[a-z_][a-z0-9_]{0,63}', name):
        _fail('IDENTIFIER_UNSUPPORTED', 'Only audited lowercase SQL identifiers are accepted.')
    return '`'+name+'`'


def _schema_name(name):
    if not isinstance(name, str) or not re.fullmatch('dragonhydra_migration_[a-z0-9][a-z0-9_]{0,42}', name):
        _fail('STAGING_SCHEMA_REQUIRED', 'Choose an explicit new schema beginning dragonhydra_migration_ and at most 64 characters.')
    return name


def _sql_tokens(sql):
    expression = re.compile(r"\s+|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[(),;]")
    position, tokens = 0, []
    for token in expression.finditer(sql or ''):
        if token.start() != position:
            _fail('SOURCE_SCHEMA_UNSUPPORTED', 'The source schema contains unsupported syntax.')
        position = token.end()
        value = token.group()
        if value.isspace():
            continue
        if value.startswith('"'):
            value = value[1:-1].replace('""', '"')
        tokens.append(value if value.startswith("'") else value.casefold())
    if position != len(sql or ''):
        _fail('SOURCE_SCHEMA_UNSUPPORTED', 'The source schema contains unsupported syntax.')
    return tokens


def _schema_signature(db):
    return [(kind, name, table, _sql_tokens(sql) if sql is not None else None)
            for kind, name, table, sql in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]


def _context_triggers():
    return [{'name': table+'_no_'+operation, 'table': table, 'operation': operation.upper(),
             'message': 'immutable cognitive '+kind}
            for table, kind in (('cognitive_records', 'record'), ('cognitive_receipts', 'receipt'))
            for operation in ('update', 'delete')]


def _verify_schema(db, profile=migration.CORE_PROFILE):
    if profile not in (migration.CORE_PROFILE, migration.CONTEXT_PROFILE):
        _fail('SOURCE_SCHEMA_UNSUPPORTED', 'The source schema profile is not audited.')
    with closing(sqlite3.connect(':memory:')) as reference:
        reference.executescript(SOURCE_DDL)
        for table, prefix in IMMUTABLE_TABLES.items():
            for operation in ('update', 'delete'):
                reference.execute(f"CREATE TRIGGER {prefix}_immutable_{operation} BEFORE {operation.upper()} ON {table} BEGIN SELECT RAISE(ABORT,'immutable'); END")
        if profile == migration.CONTEXT_PROFILE:
            from .cognition.memory import SCHEMA_SQL
            reference.executescript(SCHEMA_SQL)
        if _schema_signature(db) != _schema_signature(reference):
            _fail('SOURCE_SCHEMA_UNSUPPORTED', 'The bundle does not match the exact audited product schema profile; no SQL was generated.')


def _indexes(db, name):
    indexes = []
    for _, index, unique, origin, partial in db.execute('PRAGMA index_list('+migration._quote(name)+')'):
        if partial:
            _fail('SOURCE_SCHEMA_UNSUPPORTED', 'Partial indexes require an explicit migration design.')
        if origin == 'pk':
            continue
        columns = []
        for _, cid, column, descending, collation, key in db.execute('PRAGMA index_xinfo('+migration._quote(index)+')'):
            if not key:
                continue
            if cid < 0 or collation != 'BINARY':
                _fail('SOURCE_SCHEMA_UNSUPPORTED', 'Expression indexes or nonbinary SQLite collations are unsupported.')
            columns.append({'column': column, 'descending': bool(descending)})
        indexes.append({'name': index, 'unique': bool(unique), 'columns': columns})
    return sorted(indexes, key=lambda item: item['name'])


def _foreign_keys(db, name):
    grouped = {}
    for ident, sequence, parent, child, referenced, update, delete, match in db.execute('PRAGMA foreign_key_list('+migration._quote(name)+')'):
        value = grouped.setdefault(ident, {'name': 'fk_'+name+'_'+str(ident), 'parent_table': parent,
                                          'parts': [], 'on_update': update, 'on_delete': delete, 'match': match})
        value['parts'].append((sequence, child, referenced))
    result = []
    for ident in sorted(grouped):
        value = grouped[ident]
        parts = sorted(value.pop('parts'))
        value['columns'] = [part[1] for part in parts]
        value['parent_columns'] = [part[2] for part in parts]
        if value['on_update'] != 'NO ACTION' or value['on_delete'] != 'NO ACTION' or value['match'] != 'NONE':
            _fail('SOURCE_SCHEMA_UNSUPPORTED', 'This writer supports only the audited immediate NO ACTION foreign keys.')
        value['target_on_update'] = 'RESTRICT'
        value['target_on_delete'] = 'RESTRICT'
        result.append(value)
    return result


def _literal(value, column):
    if value is None:
        if not column['nullable']:
            _fail('NULL_NOT_ALLOWED', 'A required source value is NULL; no coercion or row omission was attempted.')
        return 'NULL'
    declared = column['source_declared_type']
    if declared == 'INTEGER':
        if type(value) is not int or not -MAX_BIGINT-1 <= value <= MAX_BIGINT:
            _fail('SOURCE_TYPE_MISMATCH', 'An INTEGER column contains a value that cannot be preserved as signed BIGINT.')
        return str(value)
    if declared == 'REAL':
        if type(value) is not float or not math.isfinite(value):
            _fail('SOURCE_TYPE_MISMATCH', 'A REAL column contains a nonfinite or incompatible value; DOUBLE conversion was refused.')
        literal = format(value, '.17g')
        if 'e' not in literal.lower():
            literal += 'e0'
        if float(literal).hex() != value.hex():
            _fail('FLOAT_ROUNDTRIP_FAILED', 'A REAL value failed the binary64 literal round-trip check.')
        return literal
    if declared == 'BLOB':
        if not isinstance(value, bytes):
            _fail('SOURCE_TYPE_MISMATCH', 'A BLOB column contains a nonbinary value; implicit conversion was refused.')
        return "X'"+value.hex()+"'"
    if declared == 'TEXT':
        if not isinstance(value, str):
            _fail('SOURCE_TYPE_MISMATCH', 'A TEXT column contains a nontext value; implicit conversion was refused.')
        raw = value.encode('utf-8')
        if column['binary_text']:
            if len(raw) > column['capacity_bytes']:
                _fail('KEY_VALUE_TOO_LONG', 'A complete UTF-8 identity exceeds its audited byte capacity; truncation and prefix uniqueness are forbidden.')
            return "X'"+raw.hex()+"'"
        return "CONVERT(X'"+raw.hex()+"' USING utf8mb4)"
    _fail('SOURCE_TYPE_UNSUPPORTED', 'The source declares a type outside INTEGER, REAL, TEXT and BLOB.')


def _default(column, value):
    if value is None:
        return None
    if re.fullmatch('-?[0-9]+', value):
        decoded = float(value) if column['source_declared_type'] == 'REAL' else int(value)
    elif re.fullmatch("'(?:[^']|'')*'", value):
        decoded = value[1:-1].replace("''", "'")
    else:
        _fail('SOURCE_DEFAULT_UNSUPPORTED', 'An unaudited default expression was refused.')
    literal = _literal(decoded, column)
    return '('+literal+')' if column['source_declared_type'] == 'TEXT' and not column['binary_text'] else literal


def _query(table):
    return 'SELECT '+','.join(migration._quote(column['name']) for column in table['columns'])+' FROM '+migration._quote(table['name'])+' ORDER BY '+','.join(migration._quote(key) for key in table['primary_key'])


def _insert(table, row):
    return 'INSERT INTO '+_identifier(table['name'])+' ('+','.join(_identifier(column['name']) for column in table['columns'])+') VALUES ('+','.join(_literal(value, column) for value, column in zip(row, table['columns']))+');\n'


def _plan(db, source_manifest):
    profile = migration.bundle_profile(source_manifest)
    _verify_schema(db, profile)
    capacities = TEXT_CAPACITIES if profile == migration.CORE_PROFILE else {**TEXT_CAPACITIES, **CONTEXT_TEXT_CAPACITIES}
    tables = []
    source_tables = {table['name']: table for table in source_manifest['tables']}
    sequences = dict(source_manifest['sequences'])
    for source in migration._tables(db):
        name = source['name']
        indexes, foreign_keys = _indexes(db, name), _foreign_keys(db, name)
        indexed = set(source['primary_key'])
        for index in indexes:
            indexed.update(item['column'] for item in index['columns'])
        for foreign in foreign_keys:
            indexed.update(foreign['columns'])
        columns = []
        for original in source['columns']:
            declared = original['declared_type']
            if declared not in ('INTEGER', 'REAL', 'TEXT', 'BLOB'):
                _fail('SOURCE_TYPE_UNSUPPORTED', 'Only audited INTEGER, REAL, TEXT and BLOB declarations are supported.')
            binary = declared == 'TEXT' and original['name'] in indexed
            capacity = capacities.get(name, {}).get(original['name']) if binary else None
            if binary and capacity is None:
                _fail('KEY_CAPACITY_UNAUDITED', 'Every text key needs an explicit audited byte capacity.')
            target = ('VARBINARY('+str(capacity)+')') if binary else {'INTEGER': 'BIGINT', 'REAL': 'DOUBLE', 'TEXT': 'LONGTEXT', 'BLOB': 'LONGBLOB'}[declared]
            column = {'name': original['name'], 'source_declared_type': declared, 'target_type': target,
                      'source_not_null': original['not_null'], 'nullable': not (original['not_null'] or original['primary_key_position']),
                      'primary_key_position': original['primary_key_position'], 'binary_text': binary,
                      'capacity_bytes': capacity, 'source_default_sql': original['default_sql'],
                      'maximum_observed_bytes': 0 if declared in ('TEXT', 'BLOB') else None, 'null_count': 0}
            column['target_default_sql'] = _default(column, original['default_sql'])
            columns.append(column)
        table = {'name': name, 'columns': columns, 'primary_key': source['primary_key'],
                 'indexes': indexes, 'foreign_keys': foreign_keys, 'row_count': 0,
                 'source_rows_sha256': source_tables[name]['rows_sha256'], 'maximum_insert_bytes': 0,
                 'auto_increment': None, 'key_audit': []}
        rows_digest = hashlib.sha256()
        for row in db.execute(_query(table)):
            statement = _insert(table, row)
            table['maximum_insert_bytes'] = max(table['maximum_insert_bytes'], len(statement.encode('utf-8')))
            table['row_count'] += 1
            digest = hashlib.sha256(migration.canonical([migration.typed_cell(value) for value in row])).digest()
            rows_digest.update(digest)
            for value, column in zip(row, columns):
                if value is None:
                    column['null_count'] += 1
                elif isinstance(value, (str, bytes)):
                    column['maximum_observed_bytes'] = max(column['maximum_observed_bytes'], len(value.encode('utf-8') if isinstance(value, str) else value))
        if table['row_count'] != source_tables[name]['row_count'] or rows_digest.hexdigest() != table['source_rows_sha256']:
            _fail('SOURCE_ROWS_CHANGED', 'Source rows differ from the verified preparation bundle.')
        if name in ('connector_observations', 'product_updates'):
            maximum = db.execute('SELECT MAX(seq) FROM '+migration._quote(name)).fetchone()[0]
            high_water = max(sequences.get(name, 0), maximum or 0, 0)
            if high_water >= MAX_BIGINT:
                _fail('SEQUENCE_EXHAUSTED', 'An AUTO_INCREMENT sequence has exhausted its signed BIGINT range.')
            table['auto_increment'] = {'column': 'seq', 'sqlite_high_water': sequences.get(name),
                                       'maximum_retained_value': maximum, 'next_value': high_water+1}
        _audit_keys(table)
        tables.append(table)
    table_map = {table['name']: table for table in tables}
    for table in tables:
        columns = {column['name']: column for column in table['columns']}
        for foreign in table['foreign_keys']:
            parent = {column['name']: column for column in table_map[foreign['parent_table']]['columns']}
            for child, target in zip(foreign['columns'], foreign['parent_columns']):
                if columns[child]['target_type'] != parent[target]['target_type']:
                    _fail('FOREIGN_KEY_TYPE_MISMATCH', 'A foreign key and its referenced column must have matching complete target types.')
    ordered, pending = [], set(table_map)
    while pending:
        ready = sorted(name for name in pending if all(key['parent_table'] not in pending for key in table_map[name]['foreign_keys']))
        if not ready:
            _fail('FOREIGN_KEY_CYCLE', 'A foreign-key cycle needs an explicitly designed loading strategy.')
        ordered.extend(ready)
        pending.difference_update(ready)
    triggers = [{'name': prefix+'_immutable_'+operation, 'table': table, 'operation': operation.upper()}
                for table, prefix in IMMUTABLE_TABLES.items() for operation in ('update', 'delete')]
    if profile == migration.CONTEXT_PROFILE:
        triggers += _context_triggers()
    # Empty or tiny datasets still contain CREATE TABLE statements. The audited
    # fixed preamble/trigger statements are below 512 bytes (identifiers <=64);
    # include those and all DDL instead of treating INSERT size as the packet bound.
    maximum = max([512, *(table['maximum_insert_bytes'] for table in tables),
                   *(len(_ddl(table).encode('utf-8')) for table in tables)])
    return {'tables': tables, 'creation_order': ordered, 'triggers': sorted(triggers, key=lambda item: item['name']),
            'maximum_statement_bytes': maximum,
            'index_limit_bytes': MAX_KEY_BYTES, 'key_capacity_policy': capacities}


def _audit_keys(table):
    columns = {column['name']: column for column in table['columns']}
    keys = [('PRIMARY', table['primary_key'])]
    keys += [(index['name'], [part['column'] for part in index['columns']]) for index in table['indexes']]
    keys += [(foreign['name'], foreign['columns']) for foreign in table['foreign_keys']]
    for name, names in keys:
        def size(column_name):
            column = columns[column_name]
            return column['capacity_bytes'] if column['binary_text'] else 8
        declared = sum(size(column) for column in names)
        physical = declared+sum(size(column) for column in table['primary_key'] if column not in names)
        if declared > MAX_KEY_BYTES or physical > MAX_KEY_BYTES:
            _fail('INDEX_BUDGET_EXCEEDED', 'An entire key exceeds the audited InnoDB byte budget; prefix indexes are forbidden.')
        table['key_audit'].append({'name': name, 'columns': names, 'declared_bytes': declared,
                                   'with_primary_key_bytes': physical, 'limit_bytes': MAX_KEY_BYTES,
                                   'prefix_lengths_used': False})


def _ddl(table):
    lines = []
    for column in table['columns']:
        declaration = _identifier(column['name'])+' '+column['target_type']
        if column['target_type'] == 'LONGTEXT':
            declaration += ' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'
        declaration += ' NULL' if column['nullable'] else ' NOT NULL'
        if table['auto_increment'] and table['auto_increment']['column'] == column['name']:
            declaration += ' AUTO_INCREMENT'
        if column['target_default_sql'] is not None:
            declaration += ' DEFAULT '+column['target_default_sql']
        lines.append(declaration)
    lines.append('PRIMARY KEY ('+','.join(_identifier(key) for key in table['primary_key'])+')')
    for index in table['indexes']:
        parts = ','.join(_identifier(part['column'])+(' DESC' if part['descending'] else ' ASC') for part in index['columns'])
        lines.append(('UNIQUE KEY ' if index['unique'] else 'KEY ')+_identifier(index['name'])+' USING BTREE ('+parts+')')
    for foreign in table['foreign_keys']:
        lines.append('CONSTRAINT '+_identifier(foreign['name'])+' FOREIGN KEY ('+','.join(_identifier(key) for key in foreign['columns'])+') REFERENCES '+_identifier(foreign['parent_table'])+' ('+','.join(_identifier(key) for key in foreign['parent_columns'])+') ON UPDATE RESTRICT ON DELETE RESTRICT')
    return 'CREATE TABLE '+_identifier(table['name'])+' (\n  '+',\n  '.join(lines)+'\n) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;\n'


def _statements(db, plan, schema, preparation_hash):
    yield ('-- DRAGONHYDRA private staging/test-only script. No application cutover.\n'
           '-- Source preparation manifest SHA256: '+preparation_hash+'\n'
           '-- Requires MariaDB >=10.11, InnoDB 16KiB pages, fail-fast client without --force.\n'
           "SET SESSION sql_mode='"+SQL_MODE+"';\n")
    yield 'SET SESSION innodb_strict_mode=ON;\n'
    yield 'SET SESSION foreign_key_checks=1;\n'
    yield 'SET SESSION unique_checks=1;\n'
    yield 'SET NAMES utf8mb4 COLLATE utf8mb4_bin;\n'
    yield 'CREATE DATABASE '+_identifier(schema)+' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n'
    yield 'USE '+_identifier(schema)+';\n'
    table_map = {table['name']: table for table in plan['tables']}
    for name in plan['creation_order']:
        yield _ddl(table_map[name])
    yield 'START TRANSACTION;\n'
    for name in plan['creation_order']:
        table = table_map[name]
        for row in db.execute(_query(table)):
            yield _insert(table, row)
    yield 'COMMIT;\n'
    for table in plan['tables']:
        if table['auto_increment']:
            yield 'ALTER TABLE '+_identifier(table['name'])+' AUTO_INCREMENT = '+str(table['auto_increment']['next_value'])+';\n'
    # Each trigger body is one SIGNAL statement; a client DELIMITER extension
    # is unnecessary. Source SELECT RAISE(ABORT,'immutable') maps to SQLSTATE.
    for trigger in plan['triggers']:
        message = trigger.get('message', 'immutable')
        yield 'CREATE TRIGGER '+_identifier(trigger['name'])+' BEFORE '+trigger['operation']+' ON '+_identifier(trigger['table'])+" FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='"+message+"';\n"
    yield "SELECT 'mariadb_staging_script_only' AS migration_status;\n"


def _source(bundle):
    bundle = migration._local(bundle)
    verified = migration.validate_bundle(bundle)
    manifest = json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    return bundle, manifest, verified


def build_script(bundle, output, schema):
    schema = _schema_name(schema)
    bundle, source, verified = _source(bundle)
    output = migration._local(output)
    if output.exists():
        _fail('OUTPUT_EXISTS', 'Choose a fresh private SQL directory; existing results are never overwritten.')
    if output.is_relative_to(bundle):
        _fail('OUTPUT_INSIDE_SOURCE_BUNDLE', 'Keep generated SQL outside the validated source bundle.')
    with closing(migration._read_only(bundle/'core.sqlite3')) as db:
        db.execute('BEGIN')
        try:
            plan = _plan(db, source)
            output.parent.mkdir(parents=True, exist_ok=True)
            migration._directory(output)
            statement_count = 0
            with migration._open_private(output/'migration.sql') as destination, migration._open_private(output/'statements.json') as statements:
                statements.write(b'[\n')
                for statement in _statements(db, plan, schema, source['manifest_sha256']):
                    destination.write(statement.encode('utf-8'))
                    if statement_count:
                        statements.write(b',\n')
                    statements.write(migration.canonical(statement))
                    statement_count += 1
                statements.write(b'\n]\n')
                destination.flush()
                statements.flush()
                os.fsync(destination.fileno())
                os.fsync(statements.fileno())
        finally:
            db.rollback()
    # Detect source-bundle drift during generation, before publishing a manifest.
    if migration.validate_bundle(bundle)['manifest_sha256'] != verified['manifest_sha256']:
        _fail('SOURCE_BUNDLE_CHANGED', 'The preparation bundle changed while SQL was being generated.')
    manifest = {
        'format_version': CONTEXT_VERSION if migration.bundle_profile(source) == migration.CONTEXT_PROFILE else VERSION,
        'status': STATUS, 'created_at': _now(), 'schema': schema,
        'executed': False, 'cutover': False, 'backend_changed': False,
        'source_bundle': bundle.relative_to(migration.ROOT).as_posix(),
        'source_manifest_sha256': source['manifest_sha256'], 'source_snapshot_sha256': verified['snapshot_sha256'],
        'source_raw_payload_count': verified['raw_payload_count'], 'source_row_count': verified['row_count'],
        'sql': {'path': 'migration.sql', **migration._digest_file(output/'migration.sql')}, 'mapping': plan,
        'statements': {'path': 'statements.json', **migration._digest_file(output/'statements.json'), 'count': statement_count},
        'target_requirements': {'engine': 'InnoDB', 'minimum_mariadb_version': '10.11',
                                'innodb_page_size_minimum': 16384, 'row_format': 'DYNAMIC',
                                'schema_must_not_exist': True, 'client_error_policy': 'fail_fast_no_force',
                                'minimum_max_allowed_packet_bytes': plan['maximum_statement_bytes']+1024,
                                'sql_mode': SQL_MODE, 'foreign_key_checks': 1, 'unique_checks': 1},
        'privacy': 'Private database contents including hashed sessions; no credentials or account statements are added to SQL.',
        'limits': ['SQL was generated and independently compared to SQLite; it has not been executed on MariaDB.',
                   'DDL is not transactionally rolled back as a group; a failed staging load must remain isolated.',
                   'Indexed TEXT becomes VARBINARY; a future backend adapter must decode UTF-8 identity bytes explicitly.',
                   'No application backend change, credential loading, production schema selection or cutover occurs.'],
        'documentation': DOCUMENTATION,
    }
    if migration.bundle_profile(source) == migration.CONTEXT_PROFILE:
        manifest['schema_profile'] = migration.CONTEXT_PROFILE
    manifest['manifest_sha256'] = hashlib.sha256(migration.canonical(manifest)).hexdigest()
    migration._write(output/'manifest.json', manifest)
    result = validate_script(output)
    migration._write(output/'verification.json', result)
    return result


def validate_script(output):
    output = migration._local(output)
    try:
        manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        profile = manifest.get('schema_profile', migration.CORE_PROFILE)
        if (not ((manifest['format_version'] == VERSION and profile == migration.CORE_PROFILE)
                 or (manifest['format_version'] == CONTEXT_VERSION and profile == migration.CONTEXT_PROFILE))
                or manifest['status'] != STATUS or manifest['executed'] or manifest['cutover'] or manifest['backend_changed']):
            _fail('SQL_MANIFEST_UNSUPPORTED', 'This is not a supported unexecuted staging SQL manifest.')
        digest = hashlib.sha256(migration.canonical({key: value for key, value in manifest.items() if key != 'manifest_sha256'})).hexdigest()
        if digest != manifest['manifest_sha256']:
            _fail('SQL_MANIFEST_CHANGED', 'The staging SQL manifest changed after generation.')
        for path in output.iterdir():
            if path.is_symlink() or not path.is_file() or path.name not in ('migration.sql', 'statements.json', 'manifest.json', 'verification.json'):
                _fail('SQL_ARTIFACT_UNEXPECTED', 'The private SQL directory contains an unexpected or linked artifact.')
        if manifest['sql']['path'] != 'migration.sql' or migration._digest_file(output/'migration.sql') != {key: manifest['sql'][key] for key in ('bytes', 'sha256')}:
            _fail('SQL_ARTIFACT_CHANGED', 'The generated SQL is absent or changed.')
        if manifest['statements']['path'] != 'statements.json' or migration._digest_file(output/'statements.json') != {key: manifest['statements'][key] for key in ('bytes', 'sha256')}:
            _fail('SQL_ARTIFACT_CHANGED', 'The ordered SQL statements are absent or changed.')
        schema = _schema_name(manifest['schema'])
        bundle, source, verified = _source(migration.ROOT/manifest['source_bundle'])
        if migration.bundle_profile(source) != profile:
            _fail('SQL_SOURCE_PROFILE_MISMATCH', 'The staging profile differs from the retained preparation profile.')
        if source['manifest_sha256'] != manifest['source_manifest_sha256'] or verified['snapshot_sha256'] != manifest['source_snapshot_sha256']:
            _fail('SQL_SOURCE_CHANGED', 'The SQL source does not match the verified preparation bundle.')
        with closing(migration._read_only(bundle/'core.sqlite3')) as db:
            plan = _plan(db, source)
            if plan != manifest['mapping']:
                _fail('SQL_MAPPING_CHANGED', 'Target mappings differ from the audited source-derived mapping.')
            expected, expected_json, count, size = hashlib.sha256(), hashlib.sha256(b'[\n'), 0, 0
            for statement in _statements(db, plan, schema, source['manifest_sha256']):
                raw = statement.encode('utf-8')
                expected.update(raw)
                if count:
                    expected_json.update(b',\n')
                expected_json.update(migration.canonical(statement))
                count += 1
                size += len(raw)
            expected_json.update(b'\n]\n')
            if expected.hexdigest() != manifest['sql']['sha256'] or size != manifest['sql']['bytes']:
                _fail('SQL_CONTENT_MISMATCH', 'SQL contents differ from a fresh generation using the retained SQLite snapshot.')
            if expected_json.hexdigest() != manifest['statements']['sha256'] or count != manifest['statements']['count']:
                _fail('SQL_CONTENT_MISMATCH', 'Ordered statements differ from a fresh generation using the retained SQLite snapshot.')
        result = {'valid': True, 'status': STATUS, 'schema': schema,
                'output': output.relative_to(migration.ROOT).as_posix(), 'sql_sha256': expected.hexdigest(),
                'sql_bytes': size, 'statement_groups': count, 'table_count': len(plan['tables']),
                'row_count': sum(table['row_count'] for table in plan['tables']),
                'trigger_count': len(plan['triggers']), 'source_manifest_sha256': source['manifest_sha256'],
                'executed': False, 'cutover': False, 'backend_changed': False, 'verified_at': _now()}
        if profile == migration.CONTEXT_PROFILE:
            result['schema_profile'] = profile
        return result
    except (MariaDBMigrationError, migration.MigrationError):
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error):
        _fail('SQL_BUNDLE_INVALID', 'The staging SQL bundle is incomplete or malformed; no database operation was attempted.')
