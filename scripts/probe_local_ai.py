"""Verify one optional existing Qwen runtime against a retained sports package.

No model download, install, global environment change or application capability
enablement. Writes only into a new project-local output directory and stops its
exact hidden child process, retaining a report even on failure.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from types import MethodType, SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dragonhydra.local_ai import (LocalAIError, SCHEMA_CONTEXT, build_context_package, build_package,
                                 canonical, infer, validate_grounding, validate_output)
from dragonhydra.product import Product
from dragonhydra.server import protect

RUNTIME = Path(r'D:\LocalAI\runtime\llama-b10665\llama-server.exe')
MODEL = Path(r'D:\LocalAI\models\Qwen3-4B-Q4_K_M\Qwen3-4B-Q4_K_M.gguf')
MODEL_SHA = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
RUNTIME_SHA = '20a83f9ed723c6307749863842657da86918e8b612a3eaa44fe635d147341550'


def private_directory(path):
    """Ensure future logs, SQLite sidecars and child directories inherit privacy."""
    if os.name == 'nt':
        user = subprocess.check_output([r'C:\Windows\System32\whoami.exe'], text=True).strip()
        result = subprocess.run([r'C:\Windows\System32\icacls.exe', str(path), '/inheritance:r',
                                 '/grant:r', user+':(OI)(CI)(F)', 'SYSTEM:(OI)(CI)(F)'], capture_output=True)
        if result.returncode:
            raise LocalAIError('AI_PROBE_PRIVATE_DIRECTORY', 'The private probe directory permissions could not be verified.')
    else:
        path.chmod(0o700)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--match-id')
    parser.add_argument('--context-record-id', help='Opt into package/3 using this exact retained context revision; requires --match-id')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-api', action='store_true', help='Use a real owned HTTP server and durable worker on an isolated SQLite backup')
    parser.add_argument('--verify-browser', action='store_true', help='Also exercise the accepted local-model dashboard branch in installed Edge; implies --verify-api')
    args = parser.parse_args(argv)
    if args.context_record_id is not None:
        import re
        if not args.match_id or not re.fullmatch('[a-f0-9]{64}', args.match_id):
            parser.error('--context-record-id requires an explicit canonical --match-id.')
        if not re.fullmatch('source_context:[a-f0-9]{64}', args.context_record_id):
            parser.error('--context-record-id must be an exact retained source_context record ID.')
        if args.verify_browser:
            parser.error('--context-record-id cannot use the legacy package/2 --verify-browser journey.')
    args.verify_api = args.verify_api or args.verify_browser
    state, output = args.state.resolve(), args.output.resolve()
    if not state.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        parser.error('State and output must stay within the project workspace.')
    if not (state / 'core.sqlite3').is_file():
        parser.error('Use an existing populated product state.')
    args.state, args.output = state, output
    return args


def readonly_product(state):
    """Only pure presentation methods; constructing this view cannot initialize a DB."""
    product = SimpleNamespace(state=Path(state), db_path=Path(state)/'core.sqlite3')
    for name in ('present', 'match_id', 'team_id', 'competition_id'):
        setattr(product, name, MethodType(getattr(Product, name), product))
    return product


def source_fingerprint(state):
    """No settings/credentials: exact source DB, sidecars, marker and raw bytes."""
    paths = [state/name for name in ('core.sqlite3', 'core.sqlite3-wal', 'core.sqlite3-shm',
                                     'REAL-CONTEXT-VERIFICATION.json')]
    raw = state/'raw'/'connectors'
    if raw.is_dir():
        paths.extend(sorted(raw.iterdir()))
    result = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(state.resolve()):
            raise LocalAIError('AI_SOURCE_PATH_INVALID', 'Source evidence must remain inside its owned state.')
        if path.is_file():
            with path.open('rb') as incoming:
                result[path.relative_to(state).as_posix()] = hashlib.file_digest(incoming, 'sha256').hexdigest()
    return result


def selected_package(state, match_id=None, context_record_id=None):
    if context_record_id is not None:
        product = readonly_product(state)
        package = build_context_package(product, match_id, context_record_id)
        # This must precede runner integrity/version checks and model startup.
        validate_grounding(product, package)
    else:
        # Preserve the existing default package/2 selection path.
        product = Product(state)
        match_id = match_id or product.matches(limit=1)['items'][0]['id']
        package = build_package(product, match_id)
    return match_id, package


def copy_context_dependencies(state, api_state, package):
    """Copy just four bounded, hash-verified payloads into the exclusive backup.

    Acquisition IDs and all clocks stay in SQLite's consistent backup. No vault,
    model settings, token or other configuration file is copied from the source.
    Full package reconstruction on the copy verifies these untrusted references.
    """
    from dragonhydra.connectors import research, statsbomb_context as binding
    from dragonhydra import source_context
    if package.get('schema_version') != SCHEMA_CONTEXT:
        raise LocalAIError('AI_CONTEXT_COPY_MISMATCH', 'Context copying requires an explicit package/3.')
    raw = api_state/'raw'/'connectors'
    raw.mkdir(parents=True, exist_ok=False)
    protect(raw)
    copied = []
    with closing(sqlite3.connect((api_state/'core.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT payload FROM cognitive_records WHERE record_id=? AND kind=?',
                         (package['evidence']['C1']['id'], source_context.KIND)).fetchone()
        if row is None:
            raise LocalAIError('AI_CONTEXT_COPY_MISSING', 'The isolated backup does not contain the selected context.')
        payload = json.loads(row[0])
        parent = payload['parent']
        references = [('catalog', parent['catalog_acquisition'], research.MAX_DOCUMENT_BYTES),
                      ('matches', parent['match_list_acquisition'], research.MAX_DOCUMENT_BYTES)]
        references.extend((role, payload['documents'][role], binding.MAX_DOCUMENT_BYTES)
                          for role in source_context.ROLES)
        for role, metadata, maximum in references:
            receipt = binding._receipt(db, metadata['id'])
            if canonical(binding._metadata(receipt)) != canonical(metadata):
                raise LocalAIError('AI_CONTEXT_COPY_MISMATCH', 'A selected acquisition differs from its retained receipt.')
            body = binding._body(state/'raw'/'connectors', receipt, maximum)
            target = raw/(receipt['sha256']+'.payload')
            with target.open('xb') as stream:
                stream.write(body)
            protect(target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != receipt['sha256']:
                raise LocalAIError('AI_CONTEXT_COPY_MISMATCH', 'A copied retained payload failed its digest check.')
            copied.append({'role':role, 'id':receipt['id'], 'sha256':receipt['sha256'],
                           'bytes':len(body), 'captured_at':receipt['captured_at']})
    validate_grounding(readonly_product(api_state), package)
    return copied


def validate_context_result(package, result, *, worker=False):
    """Resolve the accepted fact locally and compare every trusted dependency."""
    expected = validate_output(package, json.dumps({'fact_id':result.get('fact_id')}))
    observation = result.get('observations') if worker else [result.get('observation')]
    if (result.get('kind') != expected['kind'] or result.get('mode') != expected['mode']
            or result.get('match_id') != package['event']['id']
            or result.get('package_sha256') != package['package_sha256']
            or observation != [expected['observation']]
            or canonical(result.get('evidence_aliases')) != canonical(expected['evidence_aliases'])
            or canonical(result.get('evidence')) != canonical(expected['evidence'])
            or canonical(result.get('input_manifest')) != canonical(expected['input_manifest'])):
        raise LocalAIError('AI_API_RESULT_MISMATCH', 'The accepted fact or its exact source citations differ from the queued package.')
    return expected


def stamp():
    return datetime.now(timezone.utc).isoformat()


def stop_owned(process):
    if process.poll() is not None:
        return {'exit_code': process.returncode, 'already_exited': True}
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.AttachConsole.argtypes = [ctypes.c_ulong]
    kernel.AttachConsole.restype = ctypes.c_bool
    kernel.GenerateConsoleCtrlEvent.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel.GenerateConsoleCtrlEvent.restype = ctypes.c_bool
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
    handler = handler_type(lambda event: True)
    kernel.SetConsoleCtrlHandler.argtypes = [handler_type, ctypes.c_bool]
    kernel.FreeConsole()
    attached = bool(kernel.AttachConsole(process.pid))
    if attached:
        kernel.SetConsoleCtrlHandler(handler, True)
        kernel.GenerateConsoleCtrlEvent(0, 0)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            pass
        kernel.FreeConsole()
        kernel.SetConsoleCtrlHandler(handler, False)
    forced = process.poll() is None
    if forced:
        process.terminate()
        process.wait(timeout=5)
    return {'method': 'owned hidden console CTRL_C', 'forced': forced, 'exit_code': process.returncode}


def verify_api(state, output, model_url, key, match_id, report, *, verify_browser=False, context_package=None):
    """Exercise real authenticated HTTP and worker using an isolated DB backup."""
    api_state = output / 'api-state'
    api_state.mkdir()
    if context_package is not None:
        private_directory(api_state)
    else:
        protect(api_state)
    api_report = {'scope': 'Real owned source HTTP server, durable worker and real local Qwen inference',
                  'state_isolated': True, 'passed': False}
    report['api'] = api_report
    # SQLite's backup API includes the source WAL without guessing file-copy
    # consistency. All subsequent mutations belong to this exclusive probe copy.
    with closing(sqlite3.connect((state / 'core.sqlite3').as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(api_state / 'core.sqlite3')) as target:
            source.backup(target)
            pending = target.execute("UPDATE product_jobs SET status='cancelled',cancel_requested=1 "
                                     "WHERE status IN ('queued','running','interrupted')").rowcount
            target.execute('UPDATE connector_settings SET interval_seconds=0,next_due=0')
            target.commit()
    protect(api_state / 'core.sqlite3')
    api_report['copied_pending_jobs_cancelled'] = pending
    context_id = context_package['evidence']['C1']['id'] if context_package is not None else None
    if context_package is not None:
        api_report['copied_context_dependencies'] = copy_context_dependencies(state, api_state, context_package)
        api_report['context_record_id'] = context_id
        api_report['source_payloads_copied'] = True
        api_report['provider_downloads'] = False
    environment = dict(os.environ)
    packages = Path(sys.prefix) / 'Lib' / 'site-packages'
    environment['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'src'), str(packages)))
    environment['DRAGONHYDRA_LOCAL_AI_URL'] = model_url
    environment['DRAGONHYDRA_LOCAL_AI_KEY'] = key
    process, url, token, port = None, None, None, None
    stdout = (output / 'api.stdout.log').open('wb')
    stderr = (output / 'api.stderr.log').open('wb')
    opener = build_opener(ProxyHandler({}))

    def http(path, method='GET', body=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(url + '/dragon/api/v1' + path,
                          data=canonical(body) if body is not None else None,
                          headers=headers, method=method)
        with opener.open(request, timeout=8) as response:
            raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise LocalAIError('AI_API_RESPONSE_LIMIT', 'The probe API response exceeded its bound.')
            return response.status, json.loads(raw)

    try:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        launched = time.monotonic()
        # Windows venv python.exe is a launcher which spawns a second process.
        # Invoke its exact current base interpreter with the same pinned package
        # directory so the returned process handle owns the actual API runtime.
        python = sys._base_executable
        api_report['runtime'] = {'python': python, 'package_directory': str(packages)}
        process = subprocess.Popen([python, '-B', '-s', '-m', 'dragonhydra.server', '--port', '0',
                                    '--state', str(api_state)], env=environment, cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        api_report['owned_pid'] = process.pid
        endpoint = api_state / 'endpoint.json'
        while time.monotonic() - launched < 25:
            if process.poll() is not None:
                raise LocalAIError('AI_API_EXITED', 'The isolated source API exited before readiness.')
            if endpoint.exists():
                try:
                    endpoint_info = json.loads(endpoint.read_text())
                    if endpoint_info['pid'] != process.pid:
                        raise LocalAIError('AI_API_OWNERSHIP', 'The API endpoint does not belong to the owned child.')
                    url = endpoint_info['url']
                    token = json.loads((api_state / 'local-session.json').read_text())['token']
                    status, ready = http('/health/ready')
                    if status == 200 and ready['status'] == 'ready':
                        break
                except (OSError, ValueError, KeyError, URLError, TimeoutError):
                    pass
            time.sleep(.2)
        else:
            raise LocalAIError('AI_API_STARTUP_TIMEOUT', 'The isolated source API did not become ready.')
        from urllib.parse import urlsplit
        port = urlsplit(url).port
        api_report['url'], api_report['startup_seconds'] = url, round(time.monotonic() - launched, 3)
        try:
            http('/matches/' + match_id + '/analysis-package', authenticated=False)
            raise LocalAIError('AI_API_AUTH_NOT_ENFORCED', 'The analysis package endpoint did not require authentication.')
        except HTTPError as error:
            status = error.code
            error.close()
            if status != 401:
                raise LocalAIError('AI_API_AUTH_UNVERIFIED', 'The analysis package endpoint authentication check failed.') from None
        api_report['unauthenticated_package_rejected'] = True
        package_route = '/matches/' + match_id + '/analysis-package'
        if context_id is not None:
            from urllib.parse import urlencode
            package_route += '?' + urlencode({'context_record_id':context_id})
        status, package = http(package_route)
        if status != 200 or package['event']['id'] != match_id:
            raise LocalAIError('AI_API_PACKAGE_FAILED', 'The API returned a different selected event.')
        if context_package is not None and canonical(package) != canonical(context_package):
            raise LocalAIError('AI_API_PACKAGE_FAILED', 'The isolated API did not reconstruct the exact selected context package.')
        (output / 'api-sports-package.json').write_bytes(canonical(package))
        requested = time.monotonic()
        body = {'context_record_id':context_id} if context_id is not None else {}
        status, queued = http('/matches/' + match_id + '/local-explanations', 'POST', body)
        if status != 202 or queued['kind'] != 'local_explanation':
            raise LocalAIError('AI_API_JOB_NOT_QUEUED', 'The API did not create the explicit local explanation job.')
        api_report['job_id'] = queued['id']
        until = time.monotonic() + 45
        while time.monotonic() < until:
            status, job = http('/jobs/' + queued['id'])
            if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                break
            time.sleep(.2)
        else:
            raise LocalAIError('AI_API_JOB_TIMEOUT', 'The explicit API job did not finish within its probe deadline.')
        api_report['request_seconds'] = round(time.monotonic() - requested, 3)
        (output / 'api-job.json').write_bytes(canonical(job))
        result = job.get('result') or {}
        api_report['job_status'], api_report['local_ai'] = job['status'], result.get('local_ai')
        if job['status'] != 'succeeded' or not result.get('local_ai', {}).get('accepted'):
            api_report['fallback_verified'] = job['status'] == 'succeeded' and result.get('kind') == 'deterministic'
            raise LocalAIError('AI_API_OUTPUT_NOT_ACCEPTED', 'The API gracefully declined local inference; inspect the retained job result.')
        evidence_id = package['evidence']['E1']['id']
        if context_package is not None:
            accepted = validate_context_result(package, result, worker=True)
            api_report['selected_context_fact'] = 'C1' in accepted['evidence_aliases']
            for role, document in package['evidence']['C1']['documents'].items():
                status, metadata = http('/connections/statsbomb/acquisitions/' + document['id'])
                if status != 200 or any(metadata.get(field) != value for field, value in document.items()):
                    raise LocalAIError('AI_API_CITATION_FAILED', 'An exact retained context acquisition citation did not resolve.')
            api_report['context_acquisition_citations_resolved'] = True
        elif (result['kind'] != 'local_llm' or result['mode'] != 'constrained_source_fact_selection'
                or result['package_sha256'] != package['package_sha256']
                or result['observations'][0] not in package['allowed_observations']
                or result['evidence'][0]['id'] != evidence_id):
            raise LocalAIError('AI_API_RESULT_MISMATCH', 'The accepted job result does not match its queued evidence package.')
        status, retained = http('/evidence/' + evidence_id)
        if status != 200 or (retained.get('source_hash') or retained.get('raw_sha256')) != package['evidence']['E1']['source_sha256']:
            raise LocalAIError('AI_API_CITATION_FAILED', 'The accepted citation did not resolve to its retained source hash.')
        # A fresh SQLite reader confirms the terminal result is durable, beyond
        # the HTTP response or an in-memory worker callback.
        with sqlite3.connect(api_state / 'core.sqlite3') as db:
            persisted = db.execute('SELECT status,result FROM product_jobs WHERE id=?', (queued['id'],)).fetchone()
        if persisted[0] != 'succeeded' or json.loads(persisted[1]) != result:
            raise LocalAIError('AI_API_PERSISTENCE_FAILED', 'The completed job was not observed by a fresh SQLite reader.')
        api_report.update(passed=True, citation_resolved=True, terminal_job_observed_by_fresh_sqlite_reader=True,
                          evidence_id=evidence_id, package_sha256=package['package_sha256'], result=result)
        if verify_browser:
            browser_environment = dict(environment)
            browser_environment.pop('DRAGONHYDRA_LOCAL_AI_KEY', None)
            browser_environment.pop('DRAGONHYDRA_LOCAL_AI_URL', None)
            browser_output = output / 'browser'
            browser_command = [python, '-B', '-s', str(ROOT / 'tests/ui/local_ai_journey.py'),
                               '--url', url, '--state', str(api_state), '--output', str(browser_output),
                               '--expect-local', 'accepted']
            browser_started = time.monotonic()
            browser = subprocess.Popen(browser_command, cwd=ROOT, env=browser_environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)
            try:
                browser_terminal, _ = browser.communicate(timeout=150)
            except subprocess.TimeoutExpired:
                # The exact owned Python harness receives termination; it has
                # no server lifecycle privileges or model key in its process.
                browser.terminate()
                browser_terminal, _ = browser.communicate(timeout=8)
                (output / 'browser-terminal.log').write_bytes(browser_terminal)
                raise LocalAIError('AI_BROWSER_TIMEOUT', 'The accepted local-model browser journey exceeded its deadline.') from None
            (output / 'browser-terminal.log').write_bytes(browser_terminal)
            journey_path = browser_output / 'journey.json'
            journey = json.loads(journey_path.read_text(encoding='utf-8')) if journey_path.is_file() else {}
            report['browser'] = {'passed': browser.returncode == 0 and journey.get('passed', False),
                                 'exit_code': browser.returncode,
                                 'elapsed_seconds': round(time.monotonic() - browser_started, 3),
                                 'groups': journey.get('unique_group_count', 0),
                                 'expected_local': 'accepted', 'mocked_model_output': False,
                                 'evidence': str(journey_path.relative_to(ROOT))}
            if not report['browser']['passed']:
                raise LocalAIError('AI_BROWSER_FAILED', 'The accepted local-model browser journey failed; inspect its retained evidence.')
        return result
    finally:
        environment.pop('DRAGONHYDRA_LOCAL_AI_KEY', None)
        if process:
            if process.poll() is None and url and token:
                try:
                    http('/system/shutdown', 'POST', {})
                    process.wait(timeout=12)
                    api_report['shutdown'] = {'method': 'authenticated owned API shutdown', 'exit_code': process.returncode,
                                              'forced': False}
                except (OSError, URLError, TimeoutError, subprocess.TimeoutExpired):
                    api_report['shutdown'] = stop_owned(process)
            else:
                api_report['shutdown'] = stop_owned(process)
        stdout.close()
        stderr.close()
        session = api_state / 'local-session.json'
        session.unlink(missing_ok=True)
        api_report['temporary_api_token_removed'] = not session.exists()
        if port:
            with socket.socket() as check:
                try:
                    check.bind(('127.0.0.1', port))
                    api_report['owned_port_released'] = True
                except OSError:
                    api_report['owned_port_released'] = False
        api_report['passed'] = api_report['passed'] and api_report.get('owned_port_released', False) and api_report['temporary_api_token_removed']


def main():
    args = arguments()
    state, output = args.state, args.output
    output.mkdir(parents=True, exist_ok=False)
    if args.context_record_id is not None:
        private_directory(output)
    else:
        protect(output)
    report = {'schema_version': 1, 'started_at': stamp(), 'passed': False, 'status': 'RUNNING',
              'product_capability_enabled': False, 'downloads': False, 'installations': False,
              'scope': 'One constrained source-fact selection; not unconstrained sports analysis or forecasts.',
              'offline': {'local_model_file': True, 'runner_offline_flag': True,
                          'external_provider_used': False, 'airgap_verified': False}}
    source_paths = ('src/dragonhydra/local_ai.py', 'src/dragonhydra/local_ai_service.py',
                    'src/dragonhydra/api.py', 'src/dragonhydra/jobs.py', 'src/dragonhydra/product.py',
                    'src/dragonhydra/local_ai_context.py', 'src/dragonhydra/source_context.py',
                    'src/dragonhydra/cognition/memory.py', 'src/dragonhydra/connectors/statsbomb_context.py',
                    'src/dragonhydra/connectors/statsbomb_context_parser.py',
                    'scripts/probe_local_ai.py', 'tests/ui/local_ai_journey.py',
                    'src/dragonhydra/resources/web/app.js', 'src/dragonhydra/resources/web/style.css',
                    'src/dragonhydra/resources/web/index.html')
    report['source_bindings'] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                 for path in source_paths if (ROOT / path).is_file()}
    process, stdout, stderr, port, key_path = None, None, None, None, output / 'private-model-key.txt'
    source_before = None
    started = time.monotonic()
    try:
        # Context selection and full source reconstruction happen before any
        # model executable/version probe or runtime startup. The retained state
        # uses only the pure read-only presentation view in this opt-in branch.
        if args.context_record_id is not None:
            source_before = source_fingerprint(state)
            match_id, package = selected_package(state, args.match_id, args.context_record_id)
        if os.name != 'nt':
            raise LocalAIError('AI_PROBE_PLATFORM', 'This verified runtime profile is Windows-specific.')
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'total_page', 'available_page',
                                                       'total_virtual', 'available_virtual', 'extended')]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise LocalAIError('AI_MEMORY_UNKNOWN', 'Cannot verify the available memory budget.')
        report['available_ram_bytes'] = memory.available
        if memory.available < 8 * 1024**3:
            raise LocalAIError('AI_MEMORY_BUDGET', 'The compact CPU profile requires eight GiB of available RAM.')
        for path, digest in ((RUNTIME, RUNTIME_SHA), (MODEL, MODEL_SHA)):
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != digest:
                raise LocalAIError('AI_MODEL_INTEGRITY', 'The pinned local runtime or model digest changed.')
        report['model'] = {'path': str(MODEL), 'sha256': MODEL_SHA, 'bytes': MODEL.stat().st_size}
        version = subprocess.run([str(RUNTIME), '--version'], capture_output=True, text=True, timeout=25)
        if version.returncode or 'build 10665' not in version.stderr + version.stdout:
            raise LocalAIError('AI_RUNTIME_VERSION', 'The existing pinned runner version was not verified.')
        report['runtime'] = {'path': str(RUNTIME), 'sha256': RUNTIME_SHA, 'version': (version.stdout + version.stderr).strip()}
        if args.context_record_id is None:
            match_id, package = selected_package(state, args.match_id)
        (output / 'sports-package.json').write_bytes(canonical(package))
        report['package'] = {'match_id': match_id, 'package_sha256': package['package_sha256'],
                             'evidence_id': package['evidence']['E1']['id']}
        if args.context_record_id is not None:
            report['package'].update(schema_version=package['schema_version'],
                context_record_id=args.context_record_id, context_summary=package['context_summary'],
                source_readonly=True, grounding_verified_before_runtime=True)
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        key = secrets.token_urlsafe(48)
        key_path.write_text(key + '\n', encoding='utf-8')
        protect(key_path)
        argv = [str(RUNTIME), '--model', str(MODEL), '--host', '127.0.0.1', '--port', str(port),
                '--offline', '--device', 'none', '--n-gpu-layers', '0', '--threads', '4',
                '--ctx-size', '2048', '--parallel', '1', '--batch-size', '256', '--ubatch-size', '64',
                '--no-kv-offload', '--no-webui', '--no-slots', '--no-agent', '--reasoning', 'off',
                '--api-key-file', str(key_path), '--alias', 'dragonhydra-compact-local', '--timeout', '90',
                '--log-disable']
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        stdout, stderr = (output / 'server.stdout.log').open('wb'), (output / 'server.stderr.log').open('wb')
        launched = time.monotonic()
        process = subprocess.Popen(argv, cwd=RUNTIME.parent, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        report['owned_pid'], report['loopback_port'] = process.pid, port
        opener = build_opener(ProxyHandler({}))
        while True:
            if process.poll() is not None:
                raise LocalAIError('AI_RUNTIME_EXITED', 'The owned model process exited before readiness.')
            if time.monotonic() - launched > 45:
                raise LocalAIError('AI_STARTUP_TIMEOUT', 'The local model startup deadline expired.')
            try:
                with opener.open(f'http://127.0.0.1:{port}/health', timeout=2) as response:
                    if json.loads(response.read(1024)).get('status') == 'ok':
                        break
            except (OSError, URLError, TimeoutError):
                pass
            time.sleep(.2)
        report['startup_seconds'] = round(time.monotonic() - launched, 3)
        try:
            opener.open(f'http://127.0.0.1:{port}/v1/models', timeout=3).close()
            raise LocalAIError('AI_AUTH_NOT_ENFORCED', 'The isolated model endpoint did not require its key.')
        except HTTPError as error:
            status = error.code
            error.close()
            if status != 401:
                raise LocalAIError('AI_AUTH_UNVERIFIED', 'The isolated endpoint authentication check failed.') from None
        report['authentication_without_key_rejected'] = True
        requested = time.monotonic()
        if args.verify_api:
            result = verify_api(state, output, f'http://127.0.0.1:{port}', key, match_id, report,
                                verify_browser=args.verify_browser,
                                context_package=package if args.context_record_id is not None else None)
            if not report['api']['passed']:
                raise LocalAIError('AI_API_CLEANUP_FAILED', 'The API probe did not verify complete owned cleanup.')
        else:
            result = infer(package, f'http://127.0.0.1:{port}', key)
            if args.context_record_id is not None:
                accepted = validate_context_result(package, result)
                report['selected_context_fact'] = 'C1' in accepted['evidence_aliases']
        report['request_seconds'] = round(time.monotonic() - requested, 3)
        (output / 'accepted-result.json').write_bytes(canonical(result))
        report['result'] = result
        report['passed'] = True
        report['status'] = ('BROWSER_API_CONSTRAINED_OFFLINE_INFERENCE_VERIFIED' if args.verify_browser else
                            'API_CONSTRAINED_OFFLINE_INFERENCE_VERIFIED' if args.verify_api else
                            'CONSTRAINED_OFFLINE_INFERENCE_VERIFIED')
    except Exception as error:
        report['status'] = 'OPTIONAL_LOCAL_AI_UNAVAILABLE'
        report['error'] = {'code': error.code if isinstance(error, LocalAIError) else type(error).__name__,
                           'message': error.message if isinstance(error, LocalAIError) else 'Probe failed; inspect protected local diagnostics.'}
    finally:
        if process:
            report['shutdown'] = stop_owned(process)
        if stdout:
            stdout.close()
        if stderr:
            stderr.close()
        key_path.unlink(missing_ok=True)
        report['temporary_key_removed'] = not key_path.exists()
        if port:
            with socket.socket() as check:
                try:
                    check.bind(('127.0.0.1', port))
                    report['owned_port_released'] = True
                except OSError:
                    report['owned_port_released'] = False
        report['passed'] = report['passed'] and report.get('owned_port_released', False) and report['temporary_key_removed']
        if source_before is not None:
            report['source_before'] = source_before
            try:
                source_after = source_fingerprint(state)
                report['source_unchanged'] = source_before == source_after
                report['source_after'] = source_after
            except (OSError, LocalAIError):
                report['source_unchanged'] = False
            report['passed'] = report['passed'] and report['source_unchanged']
            if not report['source_unchanged']:
                report['status'] = 'SOURCE_PRESERVATION_FAILED'
                report['error'] = {'code':'AI_SOURCE_CHANGED', 'message':'Source byte preservation could not be verified.'}
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        report['finished_at'] = stamp()
        (output / 'report.json').write_bytes(canonical(report))
        print(json.dumps({key: report.get(key) for key in ('passed', 'status', 'startup_seconds', 'request_seconds',
                          'error', 'owned_port_released', 'temporary_key_removed', 'shutdown')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
