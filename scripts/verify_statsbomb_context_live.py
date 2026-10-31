"""Run exactly one real StatsBomb context job in a fresh private snapshot clone.

This command may perform the two fixed public GETs. It never starts a server,
retries a job, copies sibling credentials, or cleans up retained diagnostics.
Review the concrete source/state/output command before executing it.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from dragonhydra import migration
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_jobs as context_jobs
from dragonhydra.connectors import statsbomb_context_parser as parser, statsbomb_context_view as view
from dragonhydra.connectors.core import Transport
from dragonhydra.connectors.store import Store
from dragonhydra.jobs import Jobs
from dragonhydra.product import Product, identity

EXPECTED_SOURCE_MANIFEST = '392b4f8e9e4e512f3d7f4b2d80fcaed2ab706b10f5f18442c7a03dc31fcb29f5'
LEGACY_BASELINE = ROOT/'build/connections/context-foundation-20261031/legacy-baseline.json'
MARKER = 'REAL-CONTEXT-VERIFICATION.json'


def need(value, code):
    if not value:
        raise ValueError(code)


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return migration._digest_file(path)


def protect_directory(path):
    migration._private(path)
    if os.name == 'nt':
        user = subprocess.check_output([r'C:\Windows\System32\whoami.exe'], text=True).strip()
        result = subprocess.run([r'C:\Windows\System32\icacls.exe', str(path), '/inheritance:r', '/grant:r',
                                 user+':(OI)(CI)(F)', 'SYSTEM:(OI)(CI)(F)'], capture_output=True)
        need(result.returncode == 0, 'PRIVATE_DIRECTORY_ACL_FAILED')


def private_directory(path):
    path.mkdir()
    protect_directory(path)


def private_tree(root):
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink() and path.resolve().is_relative_to(root), 'UNEXPECTED_LINKED_ARTIFACT')
        protect_directory(path) if path.is_dir() else migration._private(path)


def write(path, value):
    migration._write(path, value)


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink() and path.resolve().is_relative_to(root), 'UNEXPECTED_LINKED_ARTIFACT')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def code_inventory():
    selected = [Path(__file__).resolve()]
    selected += [path for path in (ROOT/'src/dragonhydra').rglob('*') if path.is_file()
                 and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != 'build_info.json']
    return {path.relative_to(ROOT).as_posix():digest(path) for path in sorted(selected)}


def instance_snapshot():
    """Read process/service/listener identities; never emit command lines."""
    executable = Path(r'C:\Program Files\PowerShell\7\pwsh.exe')
    need(executable.is_file(), 'EXISTING_POWERSHELL_RUNTIME_REQUIRED')
    project = str(ROOT).replace("'", "''")
    endpoints = [ROOT/'runtime/product/endpoint.json',
        ROOT/'build/workstation/test-install/state data/kernel/endpoint.json',
        ROOT/'build/workstation/test-install/provider-a2/state data/kernel/endpoint.json']
    connections = ROOT/'runtime/connections'
    if connections.is_dir():
        endpoints += [path/'endpoint.json' for path in connections.iterdir() if path.is_dir() and not path.is_symlink()]
    endpoints = [str(path) for path in endpoints if path.is_file() and not path.is_symlink()]
    encoded_endpoints = base64.b64encode(json.dumps(endpoints).encode('utf-8')).decode('ascii')
    code = r'''
$ErrorActionPreference='Stop'
$root='PROJECT_ROOT'
$knownServices=@('DragonhydraWorkstation','DragonhydraWorkstationTest','DragonhydraProvidersA2Test')
$services=@(Get-CimInstance Win32_Service | Where-Object {
    $_.Name -in $knownServices -or ($_.State -eq 'Running' -and $_.PathName -and
        $_.PathName.IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0)
} | ForEach-Object {[pscustomobject]@{name=$_.Name;state=$_.State;pid=[int]$_.ProcessId;identity=$_.StartName}})
$allProcesses=@(Get-CimInstance Win32_Process)
$allListeners=@(Get-NetTCPConnection -State Listen)
$ids=@($services | Where-Object {$_.pid -gt 0} | ForEach-Object {$_.pid})
$ids+=@($allProcesses | Where-Object {$_.Name -in @('DRAGONHYDRA-Server.exe','DragonhydraService.exe')} | ForEach-Object {[int]$_.ProcessId})
$endpointFiles=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('ENCODED_ENDPOINTS')) | ConvertFrom-Json
foreach ($file in $endpointFiles) {
    $endpoint=Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
    $uri=[Uri]$endpoint.url
    if ($uri.Scheme -eq 'http' -and $uri.Host -eq '127.0.0.1' -and
        @($allListeners | Where-Object {$_.OwningProcess -eq $endpoint.pid -and $_.LocalPort -eq $uri.Port}).Count -gt 0) {
        $ids+=[int]$endpoint.pid
    }
}
$listeners=@($allListeners | Where-Object {$_.OwningProcess -in $ids -or $_.LocalPort -in (18732..18748)} |
    ForEach-Object {[pscustomobject]@{pid=[int]$_.OwningProcess;address=$_.LocalAddress;port=[int]$_.LocalPort}})
$ids+=@($listeners | ForEach-Object {$_.pid})
$processes=@($allProcesses | Where-Object {$_.ProcessId -ne VERIFIER_PID -and $_.ProcessId -in $ids} |
    ForEach-Object { [pscustomobject]@{pid=[int]$_.ProcessId;name=$_.Name;executable=$_.ExecutablePath;
        created=$_.CreationDate.ToUniversalTime().ToString('o')} })
[pscustomobject]@{processes=$processes;listeners=$listeners;services=$services} | ConvertTo-Json -Depth 5 -Compress
'''.replace('PROJECT_ROOT', project).replace('VERIFIER_PID', str(os.getpid())).replace('ENCODED_ENDPOINTS', encoded_endpoints)
    encoded = base64.b64encode(code.encode('utf-16le')).decode('ascii')
    completed = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                               capture_output=True, text=True, timeout=30)
    need(completed.returncode == 0, 'RUNNING_INSTANCE_METADATA_UNAVAILABLE')
    snapshot = json.loads(completed.stdout)
    need(all(item['executable'] and item['created'] for item in snapshot['processes']), 'RUNNING_INSTANCE_IDENTITY_INCOMPLETE')
    return snapshot


def preserve_instances(before, after):
    for key in ('processes', 'listeners', 'services'):
        existing = {migration.canonical(item) for item in after[key]}
        need(all(migration.canonical(item) in existing for item in before[key]), 'PRIOR_RUNNING_INSTANCE_CHANGED')


def preflight(db):
    jobs = db.execute("SELECT status,COUNT(*) FROM product_jobs GROUP BY status").fetchall()
    need(all(status in ('succeeded','failed','cancelled') for status, _ in jobs), 'NONTERMINAL_COPIED_JOB_REFUSED')
    enabled = db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds<>0').fetchone()[0]
    need(enabled == 0, 'ENABLED_COPIED_SCHEDULE_REFUSED')
    return {'copied_jobs_by_status':jobs, 'enabled_schedules':enabled}


def table_state(db):
    tables = {}
    for table in migration._tables(db):
        columns = [column['name'] for column in table['columns']]
        keys = [columns.index(key) for key in table['primary_key']]
        query = 'SELECT '+','.join(migration._quote(column) for column in columns)+' FROM '+migration._quote(table['name'])
        rows = {}
        for row in db.execute(query):
            cells = [migration.typed_cell(cell) for cell in row]
            key = migration.canonical([cells[index] for index in keys]).decode()
            rows[key] = hashlib.sha256(migration.canonical(cells)).hexdigest()
        tables[table['name']] = rows
    return tables


def preserve_tables(before, after, job_id, db):
    additions = {}
    allowed = {'connector_acquisitions':2, 'connector_attempts':1, 'product_jobs':1,
               'product_updates':4, 'cognitive_records':1, 'cognitive_receipts':1}
    for name, original in before.items():
        current = after[name]
        need(all(current.get(key) == value for key, value in original.items()), 'COPIED_TABLE_ROWS_CHANGED')
        additions[name] = len(current)-len(original)
        need(0 <= additions[name] <= allowed.get(name, 0), 'UNRELATED_TABLE_WRITE')
    need(set(after)-set(before) <= {'cognitive_records','cognitive_receipts'}, 'UNEXPECTED_TABLE_ADDED')
    for name in set(after)-set(before):
        additions[name] = len(after[name])
        need(additions[name] <= allowed[name], 'UNEXPECTED_CONTEXT_ROWS')
    need(db.execute('SELECT COUNT(*) FROM product_jobs WHERE id=?', (job_id,)).fetchone()[0] == 1, 'OWNED_JOB_MISSING')
    baseline_sequence = max((int(json.loads(key)[0][1]) for key in before['product_updates']), default=0)
    for topic, raw in db.execute('SELECT topic,payload FROM product_updates WHERE seq>?', (baseline_sequence,)):
        item = json.loads(raw)
        need(topic in ('job','data') and item.get('id',item.get('job_id')) == job_id, 'UNRELATED_JOB_EVENT')
    return additions


def response_metadata(doc):
    return {'id':doc.acquisition_id, 'sha256':doc.sha256, 'bytes':len(doc.body), 'original_url':doc.url,
            'resolved_url':doc.resolved_url, 'captured_at':doc.captured_at, 'http_status':doc.http_status,
            'content_type':doc.content_type}


@contextmanager
def count_live_requests(product, output, job, calls, requests):
    original_get, original_request = Transport.get, http.client.HTTPSConnection.request

    def counted_get(transport, url, headers=None):
        need(len(calls) < 2 and url in binding.ROLE_URLS.values() and url not in [item['url'] for item in calls], 'TRANSPORT_GET_BUDGET_EXCEEDED')
        need(not headers and transport.max_bytes == binding.MAX_DOCUMENT_BYTES and transport.follow_redirects is False
             and transport.raw_dir.resolve() == (product.state/'raw/connectors').resolve(), 'UNEXPECTED_TRANSPORT_CONFIGURATION')
        role = next(role for role, expected in binding.ROLE_URLS.items() if url == expected)
        with closing(product.connect()) as db:
            row = db.execute('SELECT result FROM connector_attempts WHERE id=? AND job_id=?', (context_jobs.attempt_id(job), job['id'])).fetchone()
            journal = json.loads(row[0]) if row else {}
            need(journal.get('roles',{}).get(role,{}).get('state') == 'intent', 'GET_WITHOUT_DURABLE_ROLE_INTENT')
        record = {'ordinal':len(calls)+1, 'role':role, 'url':url, 'started_at':now()}
        calls.append(record)
        write(output/('transport-'+str(record['ordinal'])+'-start.json'), record)
        try:
            return original_get(transport, url, headers)
        finally:
            completed = {**record, 'finished_at':now(), 'retained_responses':[response_metadata(doc) for doc in transport.documents]}
            write(output/('transport-'+str(record['ordinal'])+'-end.json'), completed)

    def counted_request(connection, method, url, body=None, headers=None, *, encode_chunked=False):
        target = getattr(connection, '_tunnel_host', None) or connection.host
        target_port = getattr(connection, '_tunnel_port', None) if getattr(connection, '_tunnel_host', None) else connection.port
        paths = {urlsplit(value).path for value in binding.ROLE_URLS.values()}
        need(method == 'GET' and target == 'raw.githubusercontent.com' and target_port == 443 and url in paths and body is None,
             'UNEXPECTED_HTTPS_REQUEST')
        need(not any(key.lower() in ('authorization','cookie','proxy-authorization') for key in (headers or {})), 'UNEXPECTED_AUTHENTICATED_REQUEST')
        need(len(requests) < 2 and url not in [item['path'] for item in requests], 'HTTPS_REQUEST_BUDGET_EXCEEDED')
        record = {'ordinal':len(requests)+1, 'method':method, 'tls_target':target, 'path':url, 'started_at':now()}
        requests.append(record)
        write(output/('https-'+str(record['ordinal'])+'-start.json'), record)
        return original_request(connection, method, url, body, headers or {}, encode_chunked=encode_chunked)

    Transport.get, http.client.HTTPSConnection.request = counted_get, counted_request
    try:
        yield
    finally:
        Transport.get, http.client.HTTPSConnection.request = original_get, original_request


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--source-bundle', type=Path, required=True)
    cli.add_argument('--state', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    source, state, output = map(migration._local, (args.source_bundle, args.state, args.output))
    need(state.is_relative_to(ROOT/'runtime/scratch') and state != ROOT/'runtime/scratch', 'ISOLATED_SCRATCH_STATE_REQUIRED')
    need(output.is_relative_to(ROOT/'build/connections') and output != ROOT/'build/connections', 'OWNED_EVIDENCE_OUTPUT_REQUIRED')
    need(not state.exists() and not output.exists() and not state.is_relative_to(output) and not output.is_relative_to(state), 'FRESH_STATE_AND_OUTPUT_REQUIRED')
    need(not any(left.is_relative_to(right) for left, right in ((state,source),(output,source),(source,state),(source,output))), 'SOURCE_DESTINATION_OVERLAP_REFUSED')
    verified = migration.validate_bundle(source)
    manifest = load(source/'manifest.json')
    need(verified['manifest_sha256'] == EXPECTED_SOURCE_MANIFEST and verified['table_count'] == 16
         and verified['raw_payload_count'] == 6, 'REVIEWED_LEGACY_SOURCE_REQUIRED')
    clone_bytes = manifest['snapshot']['bytes']+sum(item['bytes'] for item in manifest['raw_payloads'])
    required_free_bytes = clone_bytes+16*1024*1024+64*1024*1024+16*1024*1024
    disk = state.parent
    while not disk.exists(): disk = disk.parent
    need(shutil.disk_usage(disk).free >= required_free_bytes, 'INSUFFICIENT_ISOLATED_CLONE_SPACE')
    with closing(migration._read_only(source/'core.sqlite3')) as db:
        source_preflight = preflight(db)
        source_tables = table_state(db)
    legacy = load(LEGACY_BASELINE)['files']
    need(all(digest(ROOT/path) == expected for path, expected in legacy.items()), 'LEGACY_ARTIFACT_DRIFT')
    source_before, code_before, instances_before = inventory(source), code_inventory(), instance_snapshot()
    state.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    private_directory(state)
    private_directory(output)
    record = {'passed':False, 'mode':'real_statsbomb_context_verification', 'started_at':now(),
        'source_bundle':source.relative_to(ROOT).as_posix(), 'source_manifest_sha256':verified['manifest_sha256'],
        'source_snapshot_sha256':verified['snapshot_sha256'], 'state':state.relative_to(ROOT).as_posix(),
        'output':output.relative_to(ROOT).as_posix(), 'source_preflight':source_preflight,
        'clone_bytes':clone_bytes, 'required_free_bytes':required_free_bytes,
        'provider_http_authorized_by_invocation':True, 'automatic_followup_job':False,
        'service_activated':False, 'server_started':False, 'backend_changed':False}
    product = jobs = job = None
    calls, requests = [], []
    try:
        private_directory(state/'raw'); private_directory(state/'raw/connectors')
        for item in [manifest['snapshot'], *manifest['raw_payloads']]:
            original = migration._artifact(source, item['path'])
            target = state/item['path']
            with original.open('rb') as incoming, migration._open_private(target) as destination:
                shutil.copyfileobj(incoming, destination, length=256*1024)
                destination.flush(); os.fsync(destination.fileno())
            need(digest(target) == {key:item[key] for key in ('bytes','sha256')}, 'CLONED_ARTIFACT_MISMATCH')
        record['copied_files'] = inventory(state)
        need(len(record['copied_files']) == 7, 'UNEXPECTED_CLONE_CONTENTS')
        product = Product(state)
        jobs = Jobs(product)
        private_tree(state)
        with closing(migration._read_only(product.db_path)) as db:
            preflight(db)
            before = table_state(db)
            need(before == source_tables, 'COPIED_ROWS_CHANGED_DURING_INITIALIZATION')
        need(not any((state/name).exists() for name in ('vault','endpoint.json','local-session.json','joomla-bridge.json','local-ai.json')),
             'UNEXPECTED_CREDENTIAL_OR_ENDPOINT_FILE')
        record['no_sibling_credentials_vault_or_endpoints_copied'] = True
        match_id = identity('fixture', binding.PROVIDER, binding.MATCH_ID)
        payload = context_jobs.prepare(product, match_id)
        record['request'] = payload
        record['native_match_id'] = binding.MATCH_ID
        write(output/'preflight.json', {**record, 'code':code_before, 'instances':instances_before})
        job = jobs.submit('statsbomb_context', payload, 'verification:real-statsbomb-context')
        record['job_id'] = job['id']
        with closing(migration._read_only(product.db_path)) as db:
            queued = db.execute("SELECT id,kind FROM product_jobs WHERE status NOT IN ('succeeded','failed','cancelled')").fetchall()
            need(queued == [(job['id'],'statsbomb_context')], 'UNRELATED_ACTIVE_JOB_REFUSED')
        with count_live_requests(product, output, job, calls, requests):
            need(jobs.run_once(), 'SELECTED_JOB_DID_NOT_RUN')
        outcome = jobs.get(job['id'])
        record['job'] = outcome
        need(outcome['status'] == 'succeeded', 'SELECTED_CONTEXT_JOB_FAILED')
        need(len(calls) == len(requests) == 2 and outcome['attempts'] == 1, 'EXACT_TWO_REQUESTS_NOT_PROVEN')
        context = view.context(product, match_id)
        page = view.events(product, match_id, offset=0, limit=parser.MAX_PAGE)
        with closing(migration._read_only(product.db_path)) as db:
            row = db.execute('SELECT result FROM connector_attempts WHERE id=?', (context_jobs.attempt_id(job),)).fetchone()
            journal = json.loads(row[0])
            acquisitions = [product.connector_store.acquisition(binding.PROVIDER, journal['roles'][role]['acquisition']['id']) for role in binding.ROLE_URLS]
        need(context['availability'] == page['availability'] == 'available'
             and context['context_record_id'] == outcome['result']['context_record_id'], 'RETAINED_PROJECTION_UNAVAILABLE')
        need(all(item['http_status'] == 200 and item['bytes'] <= binding.MAX_DOCUMENT_BYTES for item in acquisitions), 'SUCCESSFUL_BOUNDED_RECEIPTS_REQUIRED')
        write(output/'context.json', context); write(output/'events-page.json', page)
        write(output/'acquisitions.json', acquisitions)
        record.update(passed=True, completed=True, context_record_id=context['context_record_id'],
                      event_rows=page['total'], first_page_rows=len(page['items']), successful_200_receipts=len(acquisitions))
    except BaseException as error:
        code = getattr(error, 'code', str(error))
        record['error'] = {'type':type(error).__name__, 'code':code if isinstance(code,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',code) else 'VERIFICATION_FAILED'}
    finally:
        record.update(finished_at=now(), transport_get_invocations=calls, https_request_invocations=requests,
                      request_count_semantics='Client method invocations before delegation; failed sockets do not prove delivery. Successful HTTP 200 acquisition receipts are counted separately.')
        try:
            need(inventory(source) == source_before and code_inventory() == code_before, 'SOURCE_OR_CODE_CHANGED')
            need(all(digest(ROOT/path) == expected for path, expected in legacy.items()), 'LEGACY_ARTIFACT_DRIFT')
            instances_after = instance_snapshot(); preserve_instances(instances_before, instances_after)
            record.update(source_bundle_byte_identical=True, legacy_five_artifacts_byte_identical=True,
                          source_modules_byte_identical=True, prior_running_instances_preserved=True)
            write(output/'instances-after.json', instances_after)
            if jobs is not None and job is not None:
                record['job'] = jobs.get(job['id'])
                with closing(migration._read_only(product.db_path)) as db:
                    after = table_state(db)
                    record['table_additions'] = preserve_tables(before, after, job['id'], db)
                    record['base_observations'] = {'before':len(before['connector_observations']),
                        'after':len(after['connector_observations']), 'all_original_row_hashes_unchanged':True}
                    row = db.execute('SELECT result FROM connector_attempts WHERE id=?', (context_jobs.attempt_id(job),)).fetchone()
                    journal = json.loads(row[0]) if row else None
                    receipts = []
                    if journal:
                        write(output/'attempt-journal.json', journal)
                        for entry in journal['roles'].values():
                            if entry['state'] == 'complete':
                                acquisition = Store._acquisition_row(db, entry['acquisition']['id'])
                                need(acquisition is not None and migration.canonical(Store._acquisition_metadata(acquisition)) == migration.canonical(entry['acquisition']), 'RECORDED_RECEIPT_MISMATCH')
                                receipts.append(Store._acquisition_metadata(acquisition))
                    def added_keys(name): return set(after[name])-set(before[name])
                    def row_key(value): return migration.canonical([['text',value]]).decode()
                    need(added_keys('connector_acquisitions') == {row_key(item['id']) for item in receipts}, 'UNRELATED_ACQUISITION_ADDED')
                    need(added_keys('connector_attempts') == ({row_key(context_jobs.attempt_id(job))} if journal else set()), 'UNRELATED_ATTEMPT_ADDED')
                    need(added_keys('product_jobs') == {row_key(job['id'])}, 'UNRELATED_JOB_ADDED')
                    record['successful_200_receipts'] = sum(item['http_status'] == 200 for item in receipts)
                    record['retained_response_receipts'] = len(receipts)
                    write(output/'receipts-final.json', receipts)
                record['copied_base_rows_unchanged'] = True
                need(all(digest(state/path) == expected for path, expected in record['copied_files'].items() if path.startswith('raw/')), 'COPIED_RAW_EVIDENCE_CHANGED')
                record['copied_six_raw_files_byte_identical'] = True
        except BaseException as error:
            record['passed'] = False
            record['preservation_error'] = {'type':type(error).__name__, 'code':str(error) if re.fullmatch('[A-Z][A-Z0-9_]{0,127}',str(error)) else 'PRESERVATION_CHECK_FAILED'}
        try:
            private_tree(state); private_tree(output)
            record['private_files_verified'] = True
        except BaseException as error:
            record['passed'] = False
            record['privacy_error'] = {'type':type(error).__name__, 'code':'PRIVATE_ARTIFACT_PROTECTION_FAILED'}
        record['completed'] = bool(record.get('passed'))
        write(output/'verification.json', record)
        write(state/MARKER, {key:record[key] for key in ('mode','completed','source_bundle','source_manifest_sha256','state','output','job_id','native_match_id','context_record_id') if key in record})
        print(json.dumps({'passed':record['passed'], 'state':record['state'], 'output':record['output'],
                          'job_status':record.get('job',{}).get('status'), 'transport_get_invocations':len(calls),
                          'https_request_invocations':len(requests), 'event_rows':record.get('event_rows'),
                          'error':record.get('error'), 'preservation_error':record.get('preservation_error')}, indent=2))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, migration.MigrationError) as error:
        print(json.dumps({'passed':False, 'error':getattr(error,'code',str(error)),
                          'message':'No follow-up job was created. Any isolated state already created is retained.'}))
        raise SystemExit(1)
