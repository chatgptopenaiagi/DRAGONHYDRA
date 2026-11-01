"""Bounded installed-wheel HTTP acceptance against explicitly isolated state.

The caller prepares a private database/raw snapshot and installs the wheel.
This helper never contacts providers, changes services, or copies credentials.
It also runs on Windows to produce an independently executed comparison.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


API = '/dragon/api/v1'
MATCH = '4897236dbf6d5312ff576ee18d6f4c03355e083701b4510543f36c3ad1b101a1'
CONTEXT = 'source_context:ee80300baae09fc55c61a5312abdc7553d072bcdd3c2e3dbf4ce13a2bb7466fe'
WINDOWS_PACKAGE = '60802e4502eac8a38e638d6711a302ac716d2711131c101ff221de87444a0aa6'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def executable_path(path):
    # Linux virtual environments commonly symlink bin/python to the base
    # interpreter. Resolving that link changes sys.prefix and loses the
    # installed wheel and dependencies. Preserve the caller-selected entry.
    return str(path.absolute())


def server_command(args, state):
    command = ([executable_path(args.launcher)] if args.launcher else
               [executable_path(args.python), '-I', '-B', '-m', 'dragonhydra.server'])
    return command + ['--state', str(state), '--port', '0']


def checked_endpoint(value, pid):
    url = value.get('url', '')
    parsed = urlsplit(url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
            and parsed.port and not parsed.username and not parsed.password
            and parsed.path == '' and not parsed.query and not parsed.fragment
            and value.get('pid') == pid, 'Endpoint is not owned loopback HTTP')
    return url


def run(args):
    state, output = args.state.resolve(), args.output.resolve()
    require(state.is_dir() and (state/'core.sqlite3').is_file(),
            'Caller must prepare isolated state with a retained SQLite snapshot')
    require(not output.exists() and not output.is_relative_to(state)
            and not state.is_relative_to(output), 'Fresh output outside state required')
    require(not (state/'endpoint.json').exists(), 'State already has endpoint metadata')
    # A copied scheduler or pending job could contact a provider. Refuse until
    # the caller has explicitly neutralized those on the isolated copy.
    import sqlite3
    with sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
        require(db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running','interrupted')").fetchone()[0] == 0,
                'Isolated copy still contains pending jobs')
        require(db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds<>0 OR next_due<>0').fetchone()[0] == 0,
                'Isolated copy still contains scheduled provider activity')
    output.mkdir(parents=True)
    report = {'started_at': utc(), 'passed': False,
              'scope': 'Installed Python server, real retained snapshot, HTTP, exports and restart',
              'python': executable_path(args.python), 'state': str(state),
              'harness_sha256': digest(Path(__file__).read_bytes()),
              'provider_acquisitions_requested': False, 'model_inference_requested': False,
              'checks': [], 'processes': []}
    opener, process, streams, token, base = build_opener(ProxyHandler({})), None, [], '', ''

    def check(name, **evidence):
        report['checks'].append({'name': name, 'passed': True, **evidence})

    def request(path, *, body=None, authenticated=True, expected=200):
        headers = {'Authorization': 'Bearer '+token} if authenticated else {}
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(base+API+path, data=raw, headers=headers)
        try:
            response = opener.open(req, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            require(response.status == expected,
                    f'{path} returned HTTP {response.status}, expected {expected}')
            return data

    def get(path, **kwargs):
        return json.loads(request(path, **kwargs))

    def start(index):
        nonlocal process, streams, token, base
        require(not (state/'endpoint.json').exists(), 'Stale endpoint before restart')
        environment = dict(os.environ)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'DRAGONHYDRA_LOCAL_AI_URL', 'DRAGONHYDRA_LOCAL_AI_KEY'):
            environment.pop(name, None)
        command = server_command(args, state)
        streams = [(output/f'server-{index}.stdout.log').open('w'),
                   (output/f'server-{index}.stderr.log').open('w')]
        process = subprocess.Popen(command, stdout=streams[0], stderr=streams[1], env=environment,
                                   **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        report['processes'].append({'pid': process.pid, 'command': command})
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            require(process.poll() is None, f'Server exited during startup ({process.returncode})')
            try:
                endpoint = json.loads((state/'endpoint.json').read_text())
                base = checked_endpoint(endpoint, process.pid)
                token = json.loads((state/'local-session.json').read_text())['token']
                health = get('/health/ready')
                if health['status'] == 'ready':
                    check(f'startup_{index}', endpoint=endpoint, health=health)
                    if os.name != 'nt':
                        require((state/'local-session.json').stat().st_mode & 0o777 == 0o600,
                                'Linux session file permissions are not 0600')
                    return
            except (FileNotFoundError, json.JSONDecodeError, URLError):
                pass
            time.sleep(.1)
        raise TimeoutError('Installed server readiness deadline expired')

    def stop(index):
        nonlocal process, streams
        require(get('/system/shutdown', body={})['status'] == 'stopping', 'Shutdown response differs')
        code = process.wait(timeout=45)
        report['processes'][-1]['exit_code'] = code
        require(code == 0 and not (state/'endpoint.json').exists(), 'Server did not shut down cleanly')
        for stream in streams:
            stream.close()
        streams = []
        process = None
        check(f'shutdown_{index}', exit_code=code, endpoint_removed=True)

    def job(path, body):
        queued = get(path, body=body, expected=202)
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            item = get('/jobs/'+queued['id'])
            if item['status'] in ('succeeded', 'failed', 'cancelled'):
                require(item['status'] == 'succeeded', f'Job {queued["id"]} ended {item["status"]}: {item.get("error")}')
                return item
            time.sleep(.1)
        raise TimeoutError('Durable worker job deadline expired')

    try:
        probe = subprocess.run([executable_path(args.python), '-I', '-B', '-c',
            "import json,sys,platform,importlib.metadata as m;import dragonhydra;"
            "from dragonhydra.build_meta import info;"
            "print(json.dumps({'python':sys.version,'executable':sys.executable,"
            "'platform':platform.platform(),'module':dragonhydra.__file__,'build':info(),"
            "'dependencies':{n:m.version(n) for n in ('dragonhydra','fastapi','uvicorn','openpyxl','tzdata')}}))"],
            capture_output=True, text=True, timeout=20)
        require(probe.returncode == 0, 'Installed interpreter probe failed: '+probe.stderr[-1000:])
        report['installed_environment'] = json.loads(probe.stdout)
        start(1)
        require(get('/health/live', authenticated=False)['status'] == 'alive', 'Liveness differs')
        require(get('/matches', authenticated=False, expected=401)['error']['code'] == 'AUTHENTICATION_REQUIRED', 'Auth error contract differs')
        require(get('/matches/missing', expected=404)['error']['code'] == 'MATCH_NOT_FOUND', 'Missing-match contract differs')
        require(get('/matches?limit=0', expected=422)['error']['code'] == 'VALIDATION_ERROR', 'Validation contract differs')
        check('health_and_error_contracts', liveness_http=200, unauthenticated_http=401,
              missing_match_http=404, invalid_limit_http=422)
        page = get('/matches?limit=1')
        if args.expected_records is not None:
            require(page['total'] == args.expected_records, 'Retained record count differs')
        require(page['total'] > 0, 'No retained football records')
        selected = get('/matches/'+args.match_id)
        require(selected['home']['name'] == 'Argentina' and selected['away']['name'] == 'France'
                and selected['score'] == {'home': 3, 'away': 3}, 'Retained World Cup final differs')
        check('retained_football', records=page['total'], match=selected)
        route = '/matches/'+args.match_id
        package2 = get(route+'/analysis-package')
        require(package2['schema_version'] == 'sports-evidence-package/2', 'Default package schema differs')
        package = get(route+'/analysis-package?context_record_id='+args.context_id)
        expected_package = (json.loads(args.baseline.read_text())['package_sha256']
                            if args.baseline else WINDOWS_PACKAGE)
        require(package['schema_version'] == 'sports-evidence-package/3'
                and package['package_sha256'] == expected_package, 'Windows/Linux package/3 hash mismatch')
        require(package['context_summary']['event_rows'] == 4407, 'Retained event count differs')
        require(sorted((s['team_name'], s['entries']) for s in package['context_summary']['squad_sizes'])
                == [('Argentina', 26), ('France', 24)], 'Retained squad sizes differ')
        check('package3_windows_comparison', package_sha256=package['package_sha256'],
              baseline='Explicit baseline file' if args.baseline else 'Preserved real Windows A6/source checkpoint',
              context_summary=package['context_summary'], default_schema=package2['schema_version'])
        context = get(route+'/source-context')
        require(context['availability'] == 'available', 'Retained context unavailable')
        event_page = get(route+'/source-events?offset=4400&limit=200')
        require(event_page['total'] == 4407 and len(event_page['items']) == 7, 'Event page differs')
        check('retained_context_and_event_page', context_record_id=context['context_record_id'],
              total=event_page['total'], offset=4400, rows=len(event_page['items']))
        public = get('/matches?provider=openfootball-2025-26-en1.json&limit=1')
        require(public['items'], 'Retained OpenFootball season missing')
        standings = get('/competitions/'+public['items'][0]['competition_id']+'/standings')
        require(len(standings['items']) > 1 and sum(s['played'] for s in standings['items']) > 0,
                'Retained league standings calculation is empty')
        check('standings_calculation', teams=len(standings['items']),
              played_sum=sum(s['played'] for s in standings['items']), official=standings['official'],
              table_sha256=digest(canonical(standings['items'])))
        explanation = job(route+'/explanations', {})
        require(explanation['result']['kind'] == 'deterministic'
                and explanation['result']['evidence'][0]['id'] == selected['evidence_id'],
                'Deterministic explanation provenance differs')
        check('deterministic_analysis', job_id=explanation['id'], result=explanation['result'])
        exports = []
        for kind in ('json', 'csv', 'xlsx'):
            item = job('/exports', {'match_id': args.match_id, 'format': kind})
            result = item['result']
            downloaded = request(result['download_url'].removeprefix(API))
            require(digest(downloaded) == result['sha256'], 'Export download hash differs')
            target = state/'exports'/result['filename']
            require(target.is_file() and target.read_bytes() == downloaded, 'Export file missing or differs')
            if kind == 'json':
                require(json.loads(downloaded)['match']['id'] == args.match_id, 'JSON export match differs')
            elif kind == 'xlsx':
                # Use the selected installed interpreter for resource verification,
                # because the coordinator itself may be stdlib-only.
                inspected = subprocess.run([executable_path(args.python), '-I', '-B', '-c',
                    "from openpyxl import load_workbook;import sys;w=load_workbook(sys.argv[1]);"
                    "assert 'Match' in w.sheetnames and 'Metadata' in w.sheetnames;"
                    "assert w['Match']['A2'].value==sys.argv[2];w.close()", str(target), args.match_id],
                    capture_output=True, text=True, timeout=20)
                require(inspected.returncode == 0, 'Actual XLSX validation failed: '+inspected.stderr[-1000:])
            exports.append({'format': kind, 'job_id': item['id'], 'filename': result['filename'],
                            'bytes': len(downloaded), 'sha256': result['sha256']})
        check('real_exports', items=exports)
        before = {'records': page['total'], 'match': selected,
                  'package_sha256': package['package_sha256'], 'export_jobs': [e['job_id'] for e in exports]}
        stop(1)
        start(2)
        require(get('/matches?limit=1')['total'] == before['records'], 'Records lost after restart')
        require(get(route) == before['match'], 'Retained match changed after restart')
        require(get(route+'/analysis-package?context_record_id='+args.context_id)['package_sha256'] == before['package_sha256'],
                'Context package changed after restart')
        for item in exports:
            retained = get('/jobs/'+item['job_id'])
            require(retained['status'] == 'succeeded', 'Durable export job lost after restart')
            require(digest(request(retained['result']['download_url'].removeprefix(API))) == item['sha256'],
                    'Export lost after restart')
        check('restart_persistence', records=before['records'], match_id=args.match_id,
              package_sha256=before['package_sha256'], durable_export_jobs=len(exports))
        stop(2)
        report['passed'] = True
    except BaseException as error:
        report['error'] = {'type': type(error).__name__,
                           'message': str(error).replace(token, '[REDACTED]') if token else str(error)}
    finally:
        if process is not None and process.poll() is None:
            try:
                get('/system/shutdown', body={})
                process.wait(timeout=45)
                report['cleanup'] = {'method': 'owned_authenticated_shutdown', 'exit_code': process.returncode}
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                report['cleanup'] = {'method': 'owned_subprocess_terminated', 'exit_code': process.returncode}
        for stream in streams:
            stream.close()
        report['finished_at'] = utc()
        temporary = output/'verification.json.tmp'
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        os.replace(temporary, output/'verification.json')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']),
                      'error': report.get('error'), 'report': str(output/'verification.json')}))
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True, help='Installed-wheel Python interpreter')
    parser.add_argument('--launcher', type=Path, help='Optional installed server entry point')
    parser.add_argument('--state', type=Path, required=True, help='Caller-prepared isolated snapshot; modified by acceptance')
    parser.add_argument('--output', type=Path, required=True, help='Fresh evidence directory outside state')
    parser.add_argument('--baseline', type=Path, help='Optional preserved package JSON with package_sha256')
    parser.add_argument('--expected-records', type=int)
    parser.add_argument('--match-id', default=MATCH)
    parser.add_argument('--context-id', default=CONTEXT)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
