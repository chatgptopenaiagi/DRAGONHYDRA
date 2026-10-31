"""Verify real retained context in Edge without provider or worker execution.

This script starts and stops ONLY its own random-port loopback API, with
start_worker=False. It requires the successful real-verification marker in a
project-local scratch state. Load/Refresh source-context controls are never
clicked. Sports tables/raw files must be identical before and after; ordinary
authentication session writes are expected. State and evidence are retained.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing, contextmanager
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
import threading
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
API = '/dragon/api/v1'
AUTH_TABLES = {'product_sessions','product_bridge_nonces'}
MARKER = 'REAL-CONTEXT-VERIFICATION.json'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def digest(path):
    with path.open('rb') as incoming:
        return hashlib.file_digest(incoming,'sha256').hexdigest()


def typed(value):
    if value is None:
        return ['null']
    if isinstance(value,bytes):
        return ['blob',base64.b64encode(value).decode('ascii')]
    if isinstance(value,float):
        return ['real',value.hex()]
    return ['integer' if isinstance(value,int) else 'text',value]


def snapshot(state):
    """Read one SQLite snapshot and all files in its selected raw directory."""
    with closing(sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        schema = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        tables,auth = {},{}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"'+name.replace('"','""')+'"'
            rows = sorted(canonical([typed(value) for value in row]) for row in db.execute('SELECT * FROM '+quoted))
            result = {'rows':len(rows),'sha256':hashlib.sha256(b'\n'.join(rows)).hexdigest()}
            (auth if name in AUTH_TABLES else tables)[name] = result
        refs = db.execute('SELECT sha256,raw_reference,bytes FROM connector_acquisitions').fetchall()
    raw = state/'raw'/'connectors'
    files = {}
    for path in sorted(raw.iterdir()):
        assert path.is_file() and not path.is_symlink() and path.resolve().parent == raw.resolve(), 'Raw evidence must be ordinary contained files.'
        assert path.suffix == '.payload', 'A completed retained state must not contain partial raw files.'
        files[path.name] = {'bytes':path.stat().st_size,'sha256':digest(path)}
    for sha,name,size in refs:
        assert name == sha+'.payload' and name in files, 'A referenced retained payload is absent or unsafe.'
        assert files[name] == {'bytes':size,'sha256':sha}, 'A referenced retained payload failed its hash/length check.'
    return {'schema_sha256':hashlib.sha256(canonical(schema)).hexdigest(),
            'tables':tables,'auth_tables':auth,'raw_files':files}


def display(value):
    return 'Not supplied' if value is None else str(value)


def protect_directory(path):
    """Private inherited permissions also cover browser-created cookie files."""
    if os.name == 'nt':
        user = subprocess.check_output([r'C:\Windows\System32\whoami.exe'],text=True).strip()
        result = subprocess.run([r'C:\Windows\System32\icacls.exe',str(path),'/inheritance:r','/grant:r',
            user+':(OI)(CI)(F)','SYSTEM:(OI)(CI)(F)'],capture_output=True)
        if result.returncode:
            raise RuntimeError('PRIVATE_DIRECTORY_ACL_FAILED')
    else:
        path.chmod(0o700)


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument('--state',required=True,type=Path)
    args_parser.add_argument('--output',required=True,type=Path)
    args = args_parser.parse_args()
    if sys.flags.optimize:
        raise RuntimeError('Run verification with assertions enabled.')
    state,output = args.state.resolve(),args.output.resolve()
    assert state.is_relative_to(ROOT/'runtime'/'scratch') and state != ROOT/'runtime'/'scratch', 'Choose the isolated verified scratch state.'
    assert output.is_relative_to(ROOT/'build') and output != ROOT/'build' and not output.exists(), 'Choose a fresh project build evidence directory.'
    assert not output.is_relative_to(state) and not state.is_relative_to(output)
    assert (state/'core.sqlite3').is_file() and (state/'raw'/'connectors').is_dir()
    marker_path = state/MARKER
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    assert marker.get('mode') == 'real_statsbomb_context_verification' and marker.get('completed') is True, 'Real retained verification must succeed before the browser run.'
    assert marker.get('native_match_id') == '3869685' and marker.get('state') == state.relative_to(ROOT).as_posix(), 'The successful marker must identify this exact isolated state and native match.'
    assert EDGE.is_file(), 'Use the registered installed Edge executable.'

    from dragonhydra.api import create_app
    from dragonhydra.connectors.core import Transport
    from dragonhydra.connectors import statsbomb_context_view as view
    from dragonhydra.jobs import Jobs
    from dragonhydra.product import identity
    from dragonhydra.server import protect
    from playwright.sync_api import expect, sync_playwright
    import uvicorn

    output.mkdir(parents=True)
    protect_directory(output)
    token = secrets.token_urlsafe(48)
    proof = {'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Retained-data-only Edge/API verification; no provider calls, worker execution or context load/refresh.',
        'state':str(state.relative_to(ROOT)),'groups':[],'provider_attempts':[],
        'worker_attempts':[],'browser_blocked_requests':[],'python_blocked_requests':[],
        'unexpected_mutations':[],'page_errors':[],'console_errors':[],'http_errors':[],
        'requests':[],'screenshots':[],'marker_sha256':digest(marker_path),
        'test_token_saved_in_receipt':False,'auth_session_writes_expected':True}
    sources = [ROOT/name for name in ('tests/ui/statsbomb_retained_journey.py',
        'client/desktop/web/app.js','src/dragonhydra/resources/web/app.js','src/dragonhydra/api.py',
        'src/dragonhydra/jobs.py','src/dragonhydra/connectors/statsbomb_context_view.py',
        'src/dragonhydra/connectors/statsbomb_context_parser.py','src/dragonhydra/connectors/statsbomb_context_jobs.py')]
    proof['source_hashes_before'] = {str(path.relative_to(ROOT)).replace('\\','/'):digest(path) for path in sources}
    before = snapshot(state)
    proof['before'] = before
    product_ref = SimpleNamespace(state=state,db_path=state/'core.sqlite3')
    match_id = identity('fixture','statsbomb','3869685')
    retained = view.context(product_ref,match_id)
    assert retained['availability'] == 'available', 'The selected state must contain fully verified retained context.'
    assert retained['projection']['event_summary']['row_count'] > 50, 'This pagination journey requires more than fifty retained event rows.'
    expected_context_id = retained['context_record_id']
    assert expected_context_id == marker.get('context_record_id'), 'Retained context must match the completed real-verification marker.'
    with closing(sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        job = db.execute('SELECT kind,status,result FROM product_jobs WHERE id=?',(marker.get('job_id'),)).fetchone()
        assert job and job[:2] == ('statsbomb_context','succeeded')
        assert json.loads(job[2])['context_record_id'] == expected_context_id
        assert not db.execute("SELECT 1 FROM product_jobs WHERE status NOT IN ('succeeded','failed','cancelled')").fetchone(), 'The isolated retained state must have no active jobs.'
    proof['context_record_id'] = expected_context_id
    proof['parent_observation_id'] = retained['parent_observation_id']
    proof['retained_projection_sha256'] = hashlib.sha256(canonical(retained['projection'])).hexdigest()
    pairing_path = state/'local-session.json'
    original_pairing_hash = digest(pairing_path) if pairing_path.exists() else None
    proof['test_pairing_file_created'] = original_pairing_hash is None
    listener = None
    server = None
    thread = None
    context = None
    page = None
    application = None

    def safe(value):
        return str(value).replace(token,'[REDACTED]')

    def write_json(name,value):
        path = output/name
        path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
        protect(path)

    def passed(name,**details):
        group = {'name':name,'passed':True,**details}
        proof['groups'].append(group)
        print(json.dumps(group),flush=True)

    def screenshot(target,name):
        path = output/name
        target.screenshot(path=str(path))
        protect(path)
        proof['screenshots'].append({'path':name,'sha256':digest(path)})

    def forbidden_provider(_transport,url,*_args,**_kwargs):
        proof['provider_attempts'].append(safe(urlsplit(str(url)).netloc+urlsplit(str(url)).path))
        raise AssertionError('Provider requests are forbidden in retained browser verification.')

    def forbidden_worker(*_args,**_kwargs):
        proof['worker_attempts'].append('blocked')
        raise AssertionError('Worker execution is forbidden in retained browser verification.')

    connect = socket.create_connection
    def loopback_only(address,*values,**options):
        if address[0] not in ('127.0.0.1','localhost','::1'):
            proof['python_blocked_requests'].append(safe(address[0]))
            raise AssertionError('Non-loopback Python request blocked.')
        return connect(address,*values,**options)

    def stop_owned_api():
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.ident is not None:
            thread.join(timeout=15)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=5)
        if listener is not None:
            listener.close()

    @contextmanager
    def protected_runtime():
        with patch.object(Transport,'get',forbidden_provider),patch.object(Jobs,'start',forbidden_worker), \
             patch.object(Jobs,'run_once',forbidden_worker),patch.object(Jobs,'execute',forbidden_worker), \
             patch.object(socket,'create_connection',loopback_only):
            try:
                yield
            finally:
                # Keep guards active throughout owned-server shutdown as well.
                stop_owned_api()

    try:
        with protected_runtime():
            application = create_app(state,local_token=token,bridge_secret='',start_worker=False)
            assert application.state.jobs.thread is None
            if original_pairing_hash is None:
                protect(pairing_path)
            listener = socket.socket()
            if sys.platform == 'win32':
                listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
            origin = 'http://127.0.0.1:'+str(port)
            proof['owned_api_origin'] = origin
            server = uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=port,
                log_level='error',timeout_graceful_shutdown=3))
            thread = threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
            thread.start()
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:
                time.sleep(.05)
            assert server.started, 'Owned API did not start.'

            with sync_playwright() as playwright:
                profile = output/'edge-profile'
                profile.mkdir()
                protect_directory(profile)
                context = playwright.chromium.launch_persistent_context(user_data_dir=str(profile),
                    executable_path=str(EDGE),headless=True,viewport={'width':1500,'height':1100},
                    reduced_motion='reduce',locale='en-US',service_workers='block',
                    args=['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run'])
                proof['browser'] = {'executable':str(EDGE),'version':context.browser.version}
                def route_guard(route):
                    request = route.request
                    parsed = urlsplit(request.url)
                    same_origin = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port == port
                    method,path = request.method,parsed.path
                    proof['requests'].append({'method':method,'path':safe(path)})
                    if not same_origin:
                        proof['browser_blocked_requests'].append({'method':method,'url':safe(parsed.scheme+'://'+parsed.netloc+path)})
                        route.abort()
                    elif method not in ('GET','HEAD') and not (method == 'POST' and path == API+'/session'):
                        proof['unexpected_mutations'].append({'method':method,'path':safe(path)})
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*',route_guard)
                page = context.pages[0] if context.pages else context.new_page()
                page.on('pageerror',lambda error:proof['page_errors'].append(safe(error)))
                page.on('console',lambda message:proof['console_errors'].append(safe(message.text)) if message.type == 'error' else None)
                page.on('response',lambda response:proof['http_errors'].append({'status':response.status,'url':safe(urlsplit(response.url).path)}) if response.status >= 400 else None)

                def api(path):
                    response = context.request.get(origin+API+path,timeout=20000)
                    assert response.status == 200, 'Retained API request failed: '+str(response.status)
                    return response.json()

                page.goto(origin+'/#token='+quote(token,safe=''),wait_until='domcontentloaded')
                expect(page.locator('#service-state')).to_contain_text('Server ready')
                current = api('/matches/'+match_id+'/source-context')
                assert current == retained, 'Read-only API projection differs from pre-start retained view.'
                write_json('retained-context.json',current)
                passed('Generated-token login and the owned worker-disabled API expose the exact retained context',context_record_id=expected_context_id)

                page.goto(origin+'/#match/'+match_id,wait_until='domcontentloaded')
                page.get_by_role('tab',name='Lineups',exact=True).click()
                panel = page.locator('[data-context-state="available"]')
                expect(panel).to_be_visible()
                squads = current['projection']['squads']
                for team in squads:
                    section = panel.locator('[data-source-team-id="'+str(team['team_id'])+'"]')
                    expect(section.locator('h3')).to_have_text(team['team_name'])
                    rows = section.locator('tbody tr')
                    expect(rows).to_have_count(len(team['lineup']))
                    actual = [row.locator('td').all_text_contents() for row in rows.all()]
                    expected = [[str(player['player_id']),player['player_name'],display(player.get('player_nickname')),
                        display(player.get('jersey_number')),display(player.get('country',{}).get('name'))] for player in team['lineup']]
                    assert actual == expected, 'Displayed squad entries differ from retained source projection.'
                screenshot(panel,'retained-squads.png')
                passed('Every displayed squad entry matches retained native player fields',squad_entries={str(team['team_id']):len(team['lineup']) for team in squads})

                page.get_by_role('tab',name='Statistics',exact=True).click()
                panel = page.locator('[data-context-state="available"]')
                summary = current['projection']['event_summary']
                expect(panel).to_contain_text(str(summary['row_count'])+' retained event records')
                expect(panel).to_contain_text('not official match statistics')
                teams = {team['team_id']:team['team_name'] for team in squads}
                types = {item['id']:item['name'] for item in summary['types']}
                expected = [[teams.get(group['team_id'],'Not supplied'),display(group['period']),
                    types[group['type_id']],str(group['count'])] for group in summary['counts_by_team_period_type']]
                rows = panel.locator(':scope > .table-wrap tbody tr')
                expect(rows).to_have_count(len(expected))
                assert [row.locator('td').all_text_contents() for row in rows.all()] == expected
                assert sum(group['count'] for group in summary['counts_by_team_period_type']) == summary['row_count']
                screenshot(panel,'retained-counts.png')
                passed('Every displayed team/period/type count matches retained event-row counts',event_rows=summary['row_count'],count_groups=len(expected))

                page.locator('[data-action="browse-source-events"]').click()
                def verify_page(offset):
                    data = api('/matches/'+match_id+'/source-events?offset='+str(offset)+'&limit=50')
                    assert data['availability'] == 'available' and data['context_record_id'] == expected_context_id
                    assert data['total'] == summary['row_count']
                    rows = page.locator('[data-source-events] tbody tr')
                    expect(rows).to_have_count(len(data['items']))
                    expected = [[str(event['index']),display(event.get('period')),display(event.get('timestamp')),
                        display(event.get('minute')),display(event.get('second')),display(event.get('team',{}).get('name')),
                        display(event.get('player',{}).get('name')),event['type']['name']] for event in data['items']]
                    assert [row.locator('td').all_text_contents() for row in rows.all()] == expected
                    expect(page.locator('[data-source-events]')).to_contain_text(
                        str(offset+1)+'–'+str(offset+len(data['items']))+' of '+str(data['total'])+' source records')
                    write_json('retained-events-'+str(offset)+'.json',data)
                verify_page(0)
                screenshot(page.locator('[data-source-events]'),'retained-events-first.png')
                page.get_by_role('button',name='Next events',exact=True).click()
                verify_page(50)
                screenshot(page.locator('[data-source-events]'),'retained-events-second.png')
                page.get_by_role('button',name='Previous events',exact=True).click()
                verify_page(0)
                passed('First, next and previous native event pages match exact retained API rows',offsets=[0,50,0],page_limit=50)

                page.get_by_text('Context source receipts',exact=True).click()
                for document in current['documents']:
                    expect(panel).to_contain_text(document['sha256'])
                    assert panel.locator('a').filter(has_text='Original source').evaluate_all(
                        '(links,url)=>links.some(link=>link.href===url)',document['original_url'])
                expect(panel).to_contain_text(expected_context_id)
                expect(panel).to_contain_text(current['attribution'])
                assert api('/matches/'+match_id+'/source-context') == current
                assert not proof['provider_attempts'] and not proof['worker_attempts']
                assert not proof['browser_blocked_requests'] and not proof['python_blocked_requests']
                assert not proof['unexpected_mutations']
                assert not proof['page_errors'] and not proof['console_errors'] and not proof['http_errors']
                assert application.state.jobs.thread is None
                passed('Receipt provenance and attribution remain exact; no context load, refresh, worker or provider action occurred')
                context.close()
                context = None
        proof['passed'] = True
    except Exception:
        proof['error'] = safe(traceback.format_exc())
        print(json.dumps({'passed':False,'error':proof['error']}),flush=True)
    finally:
        if context is not None:
            try:
                if page is not None:
                    screenshot(page,'failure.png')
                context.close()
            except Exception:
                proof['browser_cleanup_error'] = safe(traceback.format_exc())
                proof['passed'] = False
        stop_owned_api()
        proof['owned_api_stopped'] = thread is None or not thread.is_alive()
        try:
            after = snapshot(state)
            proof['after'] = after
            proof['sports_tables_unchanged'] = before['tables'] == after['tables']
            proof['schema_unchanged'] = before['schema_sha256'] == after['schema_sha256']
            proof['raw_files_unchanged'] = before['raw_files'] == after['raw_files']
            proof['auth_tables_changed'] = before['auth_tables'] != after['auth_tables']
            proof['marker_unchanged'] = digest(marker_path) == proof['marker_sha256']
            proof['existing_pairing_file_unchanged'] = original_pairing_hash is None or digest(pairing_path) == original_pairing_hash
            proof['source_hashes_after'] = {str(path.relative_to(ROOT)).replace('\\','/'):digest(path) for path in sources}
            proof['source_files_unchanged'] = proof['source_hashes_before'] == proof['source_hashes_after']
            if not all(proof[key] for key in ('owned_api_stopped','sports_tables_unchanged','schema_unchanged',
                'raw_files_unchanged','marker_unchanged','existing_pairing_file_unchanged','source_files_unchanged')):
                proof['passed'] = False
            if proof['passed']:
                passed('All non-auth tables, schema, raw files, marker and source hashes are unchanged; owned API stopped')
        except Exception:
            proof['postcheck_error'] = safe(traceback.format_exc())
            proof['passed'] = False
        proof['completed_at'] = datetime.now(timezone.utc).isoformat()
        # Do not re-raise browser exceptions: navigation URLs can contain the
        # generated pairing token. Saved and printed errors are sanitized.
        write_json('journey.json',json.loads(json.dumps(proof).replace(token,'[REDACTED]')))
    return 0 if proof['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
