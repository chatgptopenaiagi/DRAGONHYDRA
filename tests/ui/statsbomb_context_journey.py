"""Real Edge/API/job journey with two in-process public-provider fixtures.

Creates and stops only its isolated server. No external network or live state
is used. Transport retains the fixture bytes through its normal receipt path.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
from unittest.mock import patch
from urllib.parse import quote, urlsplit
from urllib.request import BaseHandler
from urllib.response import addinfourl

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from dragonhydra.api import create_app
from dragonhydra.connectors.core import Transport
from dragonhydra.connectors import statsbomb_context as binding
import test_statsbomb_context as fixtures
from test_statsbomb_context_parser import LINEUPS, event, raw
from playwright.sync_api import expect, sync_playwright
import uvicorn

API = '/dragon/api/v1'


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT/'build') and not output.exists()
    output.mkdir(parents=True)
    fixture = fixtures.StatsBombContextTests()
    fixture.setUp()
    assert fixture.product.state.resolve().is_relative_to(ROOT/'runtime/scratch')
    product = fixture.product
    match_id = product.match_id({'source_id':'statsbomb', 'fixture_key':'3869685'})
    events = [event(index, type={'id':30,'name':'Pass'}, **(
        {'team':{'id':779,'name':'Argentina'}, 'player':{'id':1001,'name':'Argentina Player'},
         'period':1, 'minute':0, 'second':0} if index == 1 else {})) for index in range(1,56)]
    bodies = {binding.ROLE_URLS['events']:raw(events), binding.ROLE_URLS['lineups']:raw(LINEUPS)}
    calls, groups, page_errors = [], [], []
    proof = {'passed':False, 'started_at':datetime.now(timezone.utc).isoformat(),
             'scope':'Real Edge and isolated API/jobs/SQLite; in-process provider responses, no external network',
             'groups':groups, 'page_errors':page_errors, 'provider_fixture_requests':calls,
             'live_state_changed':False, 'external_network_requests':0}
    sources = [ROOT/name for name in ('client/desktop/web/app.js','src/dragonhydra/api.py',
        'src/dragonhydra/jobs.py','src/dragonhydra/connectors/statsbomb_context_jobs.py',
        'src/dragonhydra/connectors/statsbomb_context_view.py')]
    proof['source_hashes_before'] = {str(path.relative_to(ROOT)).replace('\\','/'):
        hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    original_init = Transport.__init__
    original_connect = socket.create_connection

    class ProviderFixture(BaseHandler):
        handler_order = 100

        def https_open(self, request):
            assert request.full_url in bodies, 'Unexpected provider endpoint'
            calls.append(request.full_url)
            headers = Message()
            headers['Content-Type'] = 'application/json'
            headers['Content-Length'] = str(len(bodies[request.full_url]))
            response = addinfourl(BytesIO(bodies[request.full_url]), headers, request.full_url, 200)
            response.msg = 'OK'
            return response

    def initialize(transport, *a, **kw):
        original_init(transport, *a, **kw)
        transport.opener.add_handler(ProviderFixture())

    def loopback_only(address, *a, **kw):
        assert address[0] in ('127.0.0.1','localhost','::1'), 'External Python network request blocked'
        return original_connect(address, *a, **kw)

    def passed(name, **details):
        group = {'name':name, 'passed':True, **details}
        groups.append(group)
        print(json.dumps(group), flush=True)

    token = 'synthetic-browser-context-token-20261031-only'
    listener = socket.socket()
    if sys.platform == 'win32':
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    listener.bind(('127.0.0.1',0))
    origin = 'http://127.0.0.1:'+str(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(create_app(product.state, local_token=token),
        host='127.0.0.1', port=listener.getsockname()[1], log_level='error', timeout_graceful_shutdown=3))
    thread = threading.Thread(target=lambda:server.run(sockets=[listener]), daemon=True)
    try:
        with patch.object(Transport, '__init__', initialize), patch.object(socket, 'create_connection', loopback_only):
            thread.start()
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:
                time.sleep(.05)
            assert server.started
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                context = browser.new_context(viewport={'width':1500,'height':1100}, reduced_motion='reduce')
                context.route('**/*', lambda route:route.continue_() if urlsplit(route.request.url).hostname=='127.0.0.1' else route.abort())
                page = context.new_page()
                page.on('pageerror', lambda error:page_errors.append(str(error).replace(token,'[REDACTED]')))
                page.goto(origin+'/#token='+quote(token), wait_until='domcontentloaded')
                expect(page.locator('#service-state')).to_contain_text('Server ready')
                page.goto(origin+'/#match/'+quote(match_id), wait_until='domcontentloaded')
                page.get_by_role('tab', name='Lineups', exact=True).click()
                expect(page.locator('[data-context-state="not_requested"]')).to_be_visible()
                assert not calls
                with closing(product.connect()) as db:
                    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='cognitive_records'").fetchone()
                    observations_before = db.execute('SELECT * FROM connector_observations ORDER BY seq').fetchall()
                passed('Opening an unrequested context shows an explicit action without provider requests or optional schema creation')

                page.locator('[data-action="load-source-context"]').click()
                expect(page.locator('[data-context-state="available"]')).to_be_visible(timeout=20000)
                assert len(calls)==2 and set(calls)==set(bodies)
                expect(page.locator('[data-source-team-id="779"]')).to_contain_text('Argentina Player')
                expect(page.locator('[data-source-team-id="771"]')).to_contain_text('France Player')
                expect(page.locator('[data-source-team-id="771"]')).to_contain_text('Not supplied')
                first = context.request.get(origin+API+'/matches/'+match_id+'/source-context').json()
                assert first['projection']['event_summary']['row_count']==55
                original_documents = deepcopy(first['documents'])
                passed('The explicit job retrieves two fixture responses and displays native source squad entries', requests=2)

                page.get_by_role('tab', name='Statistics', exact=True).click()
                expect(page.locator('[data-context-state="available"]')).to_contain_text('55 retained event records')
                expect(page.locator('[data-context-state="available"]')).to_contain_text('not official match statistics')
                page.locator('[data-action="browse-source-events"]').click()
                rows = page.locator('[data-source-events] tbody tr')
                expect(rows).to_have_count(50)
                expect(rows.first).to_contain_text('Argentina Player')
                expect(rows.nth(1)).to_contain_text('Not supplied')
                passed('Source event counts and the first fifty native rows preserve supplied zero and missing fields')

                page.get_by_role('button', name='Next events', exact=True).click()
                expect(rows).to_have_count(5)
                expect(page.locator('[data-source-events]')).to_contain_text('51–55 of 55 source records')
                page.get_by_role('button', name='Previous events', exact=True).click()
                expect(rows).to_have_count(50)
                assert len(calls)==2
                passed('Event pagination reads retained bytes without additional provider requests')

                page.locator('#refresh').click()
                expect(page.locator('[data-context-state="available"]')).to_be_visible()
                assert len(calls)==2
                passed('Refreshing the view reuses retained context without downloading')

                with page.expect_response(lambda response:response.url.endswith('/source-context')
                                          and response.request.method=='POST') as submitted:
                    page.locator('[data-action="load-source-context"]').click()
                second_job = submitted.value.json()['id']
                deadline = time.monotonic()+15
                while time.monotonic()<deadline:
                    job = context.request.get(origin+API+'/jobs/'+second_job).json()
                    if job['status'] in ('succeeded','failed','cancelled'):
                        break
                    page.wait_for_timeout(50)
                assert job['status']=='succeeded', job.get('error')
                assert len(calls)==4
                expect(page.locator('.job-progress')).to_have_count(0)
                expect(page.locator('[data-context-state="available"]')).to_be_visible()
                second = context.request.get(origin+API+'/matches/'+match_id+'/source-context').json()
                assert second['context_record_id']==first['context_record_id']
                assert second['documents']==original_documents
                with closing(product.connect()) as db:
                    assert db.execute('SELECT COUNT(*) FROM cognitive_records').fetchone()[0]==1
                    assert db.execute('SELECT COUNT(*) FROM cognitive_receipts').fetchone()[0]==1
                    assert db.execute('SELECT * FROM connector_observations ORDER BY seq').fetchall()==observations_before
                passed('An explicit second job has its own two-request budget and preserves the original duplicate context and match rows')
                assert not page_errors
                page.screenshot(path=str(output/'source-context.png'), full_page=True)
                passed('The real browser completed the journey without JavaScript exceptions')
                browser.close()
        proof['passed'] = True
        return 0
    except Exception:
        proof['error'] = traceback.format_exc().replace(token,'[REDACTED]')
        raise
    finally:
        server.should_exit = True
        if thread.ident is not None:
            thread.join(timeout=45)
        listener.close()
        proof['owned_server_stopped'] = not thread.is_alive()
        proof['source_hashes_after'] = {str(path.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        proof['source_files_changed'] = proof['source_hashes_before'] != proof['source_hashes_after']
        (output/'journey.json').write_text(json.dumps(proof,indent=2)+'\n')
        fixture.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
