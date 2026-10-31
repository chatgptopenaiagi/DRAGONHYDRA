"""Explicit private-schema MariaDB roundtrip test using existing PHP/mysqlnd.

Without --apply this only validates offline artifacts. Applying requires the
reviewed raw manifest SHA-256, an exact new migration schema and a fresh output.
No password argument, temporary secret file, service change or backend cutover.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from dragonhydra import mariadb_migration, migration


def native_cell(cell):
    if cell[0] in ('null', 'int'):
        return cell
    if cell[0] == 'float':
        return ['float_bits', struct.pack('>d', float.fromhex(cell[1])).hex()]
    if cell[0] == 'text':
        return ['text_hex', cell[1].encode('utf-8').hex()]
    if cell[0] == 'blob':
        return ['blob_hex', base64.b64decode(cell[1], validate=True).hex()]
    raise ValueError('SOURCE_CELL_TYPE_UNSUPPORTED')


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_metadata(manifest, proof):
    expected = {table['name']: table for table in manifest['mapping']['tables']}
    for phase in ('metadata_before_probes', 'metadata_after_probes'):
        metadata = proof[phase]
        tables = {row['TABLE_NAME']: row for row in metadata['tables']}
        require(set(tables) == set(expected), 'TARGET_TABLE_SCOPE_MISMATCH')
        columns, indexes, foreign = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in metadata['columns']:
            columns[row['TABLE_NAME']].append(row)
        for row in metadata['indexes']:
            require(row['SUB_PART'] is None and row['INDEX_TYPE'] == 'BTREE', 'TARGET_PREFIX_OR_INDEX_TYPE_MISMATCH')
            indexes[(row['TABLE_NAME'], row['INDEX_NAME'])].append(row)
        for row in metadata['foreign_keys']:
            foreign[(row['TABLE_NAME'], row['CONSTRAINT_NAME'])].append(row)
        expected_foreign = set()
        for name, table in expected.items():
            require(tables[name]['ENGINE'] == 'InnoDB' and tables[name]['ROW_FORMAT'].lower() == 'dynamic', 'TARGET_ENGINE_MISMATCH')
            if table['auto_increment']:
                require(int(tables[name]['AUTO_INCREMENT']) == table['auto_increment']['next_value'], 'TARGET_SEQUENCE_HIGH_WATER_MISMATCH')
            require(len(columns[name]) == len(table['columns']), 'TARGET_COLUMN_COUNT_MISMATCH')
            for source, target in zip(table['columns'], columns[name]):
                require(source['name'] == target['COLUMN_NAME'], 'TARGET_COLUMN_ORDER_MISMATCH')
                kind = target['COLUMN_TYPE'].lower()
                expected_type = source['target_type'].lower()
                require(kind == expected_type or (expected_type == 'bigint' and re.fullmatch(r'bigint\([0-9]+\)', kind)), 'TARGET_COLUMN_TYPE_MISMATCH')
                require((target['IS_NULLABLE'] == 'YES') == source['nullable'], 'TARGET_NULLABILITY_MISMATCH')
                if expected_type == 'longtext':
                    require(target['CHARACTER_SET_NAME'] == 'utf8mb4' and target['COLLATION_NAME'] == 'utf8mb4_bin', 'TARGET_TEXT_COLLATION_MISMATCH')
                elif expected_type.startswith('varbinary'):
                    require(target['CHARACTER_SET_NAME'] is None and target['COLLATION_NAME'] is None, 'TARGET_BINARY_IDENTITY_MISMATCH')
            desired = [('PRIMARY', True, [{'column': key, 'descending': False} for key in table['primary_key']])]
            desired += [(index['name'], index['unique'], index['columns']) for index in table['indexes']]
            for index_name, unique, parts in desired:
                actual = indexes[(name, index_name)]
                require(len(actual) == len(parts), 'TARGET_INDEX_PART_COUNT_MISMATCH')
                for part, row in zip(parts, actual):
                    require(row['COLUMN_NAME'] == part['column'] and int(row['NON_UNIQUE']) == int(not unique), 'TARGET_INDEX_IDENTITY_MISMATCH')
                    require(row['COLLATION'] == ('D' if part['descending'] else 'A'), 'TARGET_INDEX_DIRECTION_MISMATCH')
            for key in table['foreign_keys']:
                identity = (name, key['name']); expected_foreign.add(identity)
                actual = foreign[identity]
                require(len(actual) == len(key['columns']), 'TARGET_FOREIGN_KEY_ARITY_MISMATCH')
                for offset, row in enumerate(actual):
                    require(row['COLUMN_NAME'] == key['columns'][offset]
                            and row['REFERENCED_TABLE_NAME'] == key['parent_table']
                            and row['REFERENCED_COLUMN_NAME'] == key['parent_columns'][offset]
                            and row['REFERENCED_TABLE_SCHEMA'] == manifest['schema']
                            and row['UPDATE_RULE'] == row['DELETE_RULE'] == 'RESTRICT', 'TARGET_FOREIGN_KEY_MISMATCH')
        require(set(foreign) == expected_foreign, 'TARGET_FOREIGN_KEY_SCOPE_MISMATCH')
        triggers = {row['TRIGGER_NAME']: row for row in metadata['triggers']}
        require(set(triggers) == {row['name'] for row in manifest['mapping']['triggers']}, 'TARGET_TRIGGER_SCOPE_MISMATCH')
        for item in manifest['mapping']['triggers']:
            actual = triggers[item['name']]
            message = re.escape(item.get('message', 'immutable'))
            require(actual['EVENT_OBJECT_TABLE'] == item['table'] and actual['EVENT_MANIPULATION'] == item['operation']
                    and actual['ACTION_TIMING'] == 'BEFORE'
                    and re.fullmatch(r"SIGNAL\s+SQLSTATE\s+'45000'\s+SET\s+MESSAGE_TEXT\s*=\s*'"+message+r"'\s*;?",
                                     actual['ACTION_STATEMENT'], re.IGNORECASE), 'TARGET_IMMUTABILITY_TRIGGER_MISMATCH')


def compare_rows(source_bundle, manifest, work, proof):
    source_manifest = json.loads((source_bundle/'manifest.json').read_text())
    source_tables = {table['name']: table for table in source_manifest['tables']}
    results = []
    for table in proof['tables']:
        name = table['name']; source = source_tables[name]
        actual_path = migration._artifact(work, table['path'])
        require(migration._digest_file(actual_path)['sha256'] == table['sha256'], 'TARGET_EXPORT_HASH_MISMATCH')
        count, digest = 0, hashlib.sha256()
        with migration._artifact(source_bundle, source['path']).open('rb') as expected, actual_path.open('rb') as actual:
            for ordinal, (left, right) in enumerate(zip_longest(expected, actual), 1):
                require(left is not None and right is not None, 'ROW_COUNT_MISMATCH: '+name)
                cells = [native_cell(cell) for cell in json.loads(left)['values']]
                require(json.loads(right) == {'values': cells}, 'TYPED_ROW_MISMATCH: '+name+' row '+str(ordinal))
                digest.update(hashlib.sha256(migration.canonical(cells)).digest()); count += 1
        require(count == source['row_count'] == table['row_count'], 'ROW_COUNT_MISMATCH: '+name)
        results.append({'name': name, 'row_count': count, 'native_typed_rows_sha256': digest.hexdigest(),
                        'source_typed_rows_sha256': source['rows_sha256'], 'passed': True})
    require({item['name'] for item in results} == set(source_tables), 'TARGET_EXPORT_TABLE_SCOPE_MISMATCH')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sql-bundle', type=Path, required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--apply', action='store_true', help='Create the explicitly named absent test schema and preserve it after verification')
    parser.add_argument('--reviewed-manifest-sha256', help='Exact raw manifest.json SHA-256 reviewed before --apply')
    parser.add_argument('--output', type=Path, help='Fresh private project-local verification directory')
    parser.add_argument('--config', type=Path, default=ROOT/'build/workstation/test-install/state data/workstation.json')
    args = parser.parse_args()
    sql_bundle = migration._local(args.sql_bundle)
    verification = mariadb_migration.validate_script(sql_bundle)
    manifest = json.loads((sql_bundle/'manifest.json').read_text())
    require(args.schema == manifest['schema'], 'EXPLICIT_SCHEMA_MISMATCH')
    manifest_hash = migration._digest_file(sql_bundle/'manifest.json')['sha256']
    if not args.apply:
        print(json.dumps({'valid': True, 'executed': False, 'schema': args.schema,
                          'schema_profile': manifest.get('schema_profile', migration.CORE_PROFILE),
                          'review_manifest_sha256': manifest_hash, 'offline_validation': verification}, indent=2))
        return 0
    require(args.output is not None and args.reviewed_manifest_sha256 == manifest_hash, 'APPLY_REQUIRES_FRESH_OUTPUT_AND_REVIEWED_MANIFEST_HASH')
    config = migration._local(args.config)
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    install, state = migration._local(cfg['install_root']), migration._local(cfg['state_root'])
    require(config.parent == state and cfg['kernel_backend'] == 'sqlite', 'PRIVATE_INSTANCE_CONFIG_MISMATCH')
    php, ini = install/'web/php/php.exe', state/'web-config/php.ini'
    require(php.is_file() and ini.is_file(), 'EXISTING_PRIVATE_PHP_RUNTIME_REQUIRED')
    work = migration._local(args.output)
    source_bundle = migration._local(ROOT/manifest['source_bundle'])
    require(not work.exists() and not any(work.is_relative_to(path) for path in (sql_bundle, source_bundle, install, state)), 'FRESH_ISOLATED_VERIFICATION_OUTPUT_REQUIRED')
    work.parent.mkdir(parents=True, exist_ok=True); migration._directory(work); migration._directory(work/'rows')
    for path in [work/'php-result.json', work/'php.stdout.txt', work/'php.stderr.txt'] + [work/'rows'/(table['name']+'.jsonl') for table in manifest['mapping']['tables']]:
        with migration._open_private(path):
            pass
    command = [str(php), '-c', str(ini), str(ROOT/'tests/installation/mariadb_roundtrip.php'), '--apply',
               '--config', str(config), '--bundle', str(sql_bundle), '--schema', args.schema,
               '--output', str(work), '--reviewed-manifest-sha256', manifest_hash]
    result = {'passed': False, 'schema': args.schema, 'reviewed_manifest_sha256': manifest_hash,
              'schema_profile': manifest.get('schema_profile', migration.CORE_PROFILE),
              'command': command, 'cutover': False, 'application_authority': 'sqlite',
              'schema_preserved_after_test': True, 'source_snapshot_sha256': manifest['source_snapshot_sha256']}
    try:
        with (work/'php.stdout.txt').open('wb') as output, (work/'php.stderr.txt').open('wb') as errors:
            completed = subprocess.run(command, cwd=ROOT, stdout=output, stderr=errors, timeout=180)
        result['php_exit_code'] = completed.returncode
        proof = json.loads((work/'php-result.json').read_text())
        result['php_proof'] = 'php-result.json'
        require(completed.returncode == 0 and proof['passed'], 'PRIVATE_SCHEMA_IMPORT_OR_PROBES_FAILED')
        require(proof['reviewed_manifest_sha256'] == manifest_hash and proof['schema'] == args.schema, 'PHP_PROOF_IDENTITY_MISMATCH')
        verify_metadata(manifest, proof)
        result['tables'] = compare_rows(source_bundle, manifest, work, proof)
        require(proof['probes'] and all(item['passed'] and item['rolled_back'] for item in proof['probes']), 'ROLLBACK_CONSTRAINT_PROBE_FAILED')
        result.update(passed=True, row_count=sum(table['row_count'] for table in result['tables']),
                      table_count=len(result['tables']), probe_count=len(proof['probes']),
                      metadata_verified=True, exact_integer_text_blob_and_binary64_verified=True)
        # Revalidate all offline source/SQL bytes after the database roundtrip.
        require(mariadb_migration.validate_script(sql_bundle)['sql_sha256'] == verification['sql_sha256'], 'OFFLINE_ARTIFACTS_CHANGED_DURING_TEST')
    except Exception as error:
        result['error'] = str(error) if isinstance(error, ValueError) else type(error).__name__
        raise
    finally:
        migration._write(work/'verification.json', result)
        print(json.dumps({key: result.get(key) for key in ('passed','schema','table_count','row_count','probe_count','error')}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'passed': False, 'error': str(error) if isinstance(error, ValueError) else type(error).__name__,
                          'message': 'No authority cutover. Any newly created test schema is retained for inspection.'}))
        sys.exit(1)
