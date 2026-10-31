"""Real Edge/API/jobs with SYNTHETIC retained rows and model selection only.

No Qwen/model runner or provider HTTP is used. The script starts/stops only its
own random-port loopback API and worker over a disposable project-local state.
Run only after the corresponding API/dashboard source has been declared stable.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import traceback
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'tests')]
API = '/dragon/api/v1'
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT/'build/connections') and output != ROOT/'build/connections'
    assert not output.exists(), 'Use fresh evidence output.'
    assert EDGE.is_file(), 'Registered Edge executable unavailable.'
    output.mkdir(parents=True)
    from statsbomb_retained_journey import protect_directory, snapshot
    protect_directory(output)
    from dragonhydra import local_ai
    from dragonhydra.api import create_app
    from dragonhydra.connectors.core import Transport
    from test_local_ai_context_service import LocalAIContextServiceTests
    from playwright.sync_api import expect, sync_playwright
    import uvicorn

    token = secrets.token_urlsafe(40)
    key = secrets.token_urlsafe(40)
    mode = {'configured':True,'abort_next_context_post':False,'terminal_next_inference':False,
            'context_response':'actual','expected_transport_error':False}
    proof = {'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Real Edge/API/jobs with SYNTHETIC retained four-event context and validated fake model selection; no Qwen inference.',
        'groups':[],'requests':[],'submitted_jobs':[],'fake_inference_calls':[],
        'provider_attempts':[],'external_network_attempts':[],'page_errors':[],
        'unexpected_console_errors':[],'expected_console_errors':[],'blocked_browser_requests':[],
        'unexpected_mutations':[],'screenshots':[],'live_state_changed':False,'service_actions':0,
        'model_runner_started':False,'model_inference':False,'secrets_saved_in_receipt':False,
        'synthetic_ui_status_overrides':[]}
    sources = [ROOT/name for name in ('client/desktop/web/app.js','src/dragonhydra/resources/web/app.js',
        'src/dragonhydra/api.py','src/dragonhydra/api_contracts.py','src/dragonhydra/jobs.py',
        'src/dragonhydra/local_ai.py','src/dragonhydra/local_ai_context.py','src/dragonhydra/local_ai_service.py',
        'src/dragonhydra/source_context.py','tests/ui/local_ai_context_journey.py')]
    proof['source_hashes_before'] = {path.relative_to(ROOT).as_posix():digest(path) for path in sources}
    fixture = LocalAIContextServiceTests('test_unconfigured_context_falls_back_to_status_with_parent_only_and_all_input_ids')
    server = thread = listener = application = context = browser = None
    original_connect = socket.create_connection

    def safe(value):
        return str(value).replace(token,'[REDACTED]').replace(key,'[REDACTED]')

    def provider_forbidden(*a,**kw):
        proof['provider_attempts'].append('Transport.get')
        raise AssertionError('Provider HTTP forbidden in this browser journey')

    def loopback_only(address,*a,**kw):
        if address[0] not in ('127.0.0.1','localhost','::1'):
            proof['external_network_attempts'].append('non-loopback Python connection')
            raise AssertionError('External Python network forbidden')
        return original_connect(address,*a,**kw)

    def effective(settings):
        assert settings.state.resolve() == fixture.product.state.resolve()
        return ('http://127.0.0.1:1',key) if mode['configured'] else ('',None)

    def fake_infer(package,endpoint,credential,**kwargs):
        assert credential == key and endpoint == 'http://127.0.0.1:1'
        kwargs['check']()
        proof['fake_inference_calls'].append({'schema_version':package['schema_version'],
            'package_sha256':package['package_sha256'],'kind':'SYNTHETIC validated selection; no model'})
        if mode['terminal_next_inference']:
            mode['terminal_next_inference'] = False
            raise ValueError('SYNTHETIC terminal inference fixture')
        if package['schema_version'] == local_ai.SCHEMA_CONTEXT:
            fact = next(item for item in package['allowed_facts'] if item['evidence_aliases'] == ['E1','C1'])
            content = json.dumps({'fact_id':fact['fact_id']})
        else:
            content = json.dumps({'observation':package['allowed_observations'][0],'evidence_alias':'E1'})
        return {**local_ai.validate_output(package,content),
                'runtime':{'interface':'SYNTHETIC/browser-fixture','local_endpoint':True,'model_executed':False}}

    def passed(name,**details):
        item = {'name':name,'passed':True,**details}
        proof['groups'].append(item)
        print(json.dumps(item),flush=True)

    def screenshot(page,name):
        page.evaluate("""() => {
          const note=document.createElement('p');note.dataset.browserFixtureLabel='';
          note.textContent='SYNTHETIC browser fixture — validated fact selection; no Qwen/model inference.';
          document.querySelector('main').prepend(note);
        }""")
        path = output/name
        page.screenshot(path=str(path),full_page=True)
        proof['screenshots'].append({'path':name,'sha256':digest(path),'fixture_label_added_for_screenshot':True})
        page.locator('[data-browser-fixture-label]').evaluate_all('(nodes) => nodes.forEach(node=>node.remove())')

    def canonical_package(package):
        unsigned = {name:value for name,value in package.items() if name != 'package_sha256'}
        assert hashlib.sha256(local_ai.canonical(unsigned)).hexdigest() == package['package_sha256']
        assert len(local_ai.canonical(package)) <= 16*1024

    try:
        fixture.setUp()
        protect_directory(fixture.product.state)
        expected_package = fixture.package
        context_id,match_id = fixture.context['record_id'],fixture.match_id
        match_path = API+'/matches/'+match_id
        context_path = match_path+'/source-context'
        package_path = match_path+'/analysis-package'
        expected_manifest = fixture.manifest()
        application = create_app(fixture.product.state,local_token=token,start_worker=True)
        baseline = snapshot(fixture.product.state)
        listener = socket.socket()
        if sys.platform == 'win32':listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
        origin = 'http://127.0.0.1:'+str(port)
        proof['owned_api_origin'] = origin
        proof['synthetic_context_record_id'] = context_id
        server = uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=port,
            log_level='error',timeout_graceful_shutdown=3))
        thread = threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
        with patch.object(Transport,'get',side_effect=provider_forbidden), \
             patch.object(socket,'create_connection',side_effect=loopback_only), \
             patch('dragonhydra.local_ai_service.Settings.effective',effective), \
             patch('dragonhydra.local_ai.infer',side_effect=fake_infer):
            thread.start()
            deadline = time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
            assert server.started, 'Owned API failed to start'
            with sync_playwright() as playwright:
                profile = output/'edge-profile'
                profile.mkdir();protect_directory(profile)
                context = playwright.chromium.launch_persistent_context(user_data_dir=str(profile),
                    executable_path=str(EDGE),headless=True,viewport={'width':1500,'height':1100},
                    reduced_motion='reduce',locale='en-US',service_workers='block',
                    args=['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run'])
                proof['browser'] = {'executable':str(EDGE),'version':context.browser.version}
                page = context.pages[0] if context.pages else context.new_page()
                page.on('pageerror',lambda error:proof['page_errors'].append(safe(error)))
                def console(message):
                    if message.type != 'error':return
                    value = safe(message.text)
                    expected = (mode['expected_transport_error'] and ('ERR_FAILED' in value or 'Failed to fetch' in value)) or (mode['context_response']=='404' and '404' in value)
                    proof['expected_console_errors' if expected else 'unexpected_console_errors'].append(value)
                page.on('console',console)

                def routes(route):
                    request = route.request
                    parsed = urlsplit(request.url)
                    same = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port == port
                    entry = {'method':request.method,'path':parsed.path,'query':parsed.query}
                    proof['requests'].append(entry)
                    if not same:
                        proof['blocked_browser_requests'].append({'method':request.method,'path':safe(parsed.scheme+'://'+parsed.netloc+parsed.path)})
                        route.abort();return
                    allowed_post = parsed.path in (API+'/session',match_path+'/local-explanations',match_path+'/explanations')
                    if request.method not in ('GET','HEAD') and not (request.method=='POST' and allowed_post):
                        proof['unexpected_mutations'].append(entry);route.abort();return
                    if request.method == 'GET' and parsed.path == context_path and mode['context_response'] != 'actual':
                        if mode['context_response']=='404':
                            route.fulfill(status=404,content_type='application/json',body=json.dumps({'error':{'code':'SYNTHETIC_OLDER_API','message':'Synthetic older API fixture.'}}));return
                        value = deepcopy(retained)
                        value['availability'] = 'available' if mode['context_response']=='available_wrong_parent' else mode['context_response']
                        if value['availability'] not in ('parent_changed','available'):value['projection'] = None
                        if value['availability']=='parent_changed' or mode['context_response']=='available_wrong_parent':
                            value['context_parent_observation_id']='f'*64
                        route.fulfill(status=200,content_type='application/json',body=json.dumps(value));return
                    if request.method=='POST' and parsed.path in (match_path+'/local-explanations',match_path+'/explanations'):
                        submission = {'path':parsed.path,'payload':request.post_data_json,
                                      'idempotency_key':request.headers.get('idempotency-key')}
                        proof['submitted_jobs'].append(submission)
                        if mode['abort_next_context_post'] and submission['payload'].get('context_record_id'):
                            mode['abort_next_context_post'] = False
                            response = route.fetch()
                            assert response.status == 202
                            submission['queued_job_id_before_browser_abort'] = response.json()['id']
                            route.abort('failed');return
                    route.continue_()
                context.route('**/*',routes)

                def api(path):
                    response = context.request.get(origin+API+path,timeout=20000)
                    assert response.status==200, 'Owned API GET failed: '+str(response.status)
                    return response.json()
                def jobs_count():
                    with closing(application.state.product.connect()) as db:
                        return db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]
                def job_wait(job_id):
                    end=time.monotonic()+15
                    while time.monotonic()<end:
                        job=api('/jobs/'+job_id)
                        if job['status'] in ('succeeded','failed','cancelled','interrupted'):return job
                        page.wait_for_timeout(50)
                    raise AssertionError('Owned job did not reach a terminal state')
                def default_enabled():
                    for action in ('explain','local-explain','configure-local-model','export-sports-package'):
                        expect(page.locator('[data-action="'+action+'"]').first).to_be_enabled()
                def open_analysis():
                    page.goto(origin+'/#match/'+match_id,wait_until='domcontentloaded')
                    page.get_by_role('tab',name='Analysis',exact=True).click()
                    default_enabled()
                def submit(action):
                    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith(('/local-explanations','/explanations'))) as response:
                        page.locator('[data-action="'+action+'"]').click()
                    assert response.value.status==202
                    job=job_wait(response.value.json()['id'])
                    if job['status']=='succeeded':expect(page.locator('.job-progress')).to_have_count(0,timeout=15000)
                    return job
                def exported(action,name):
                    with page.expect_download() as downloading:
                        page.locator('[data-action="'+action+'"]').click()
                    download=downloading.value
                    path=output/name;download.save_as(str(path))
                    value=json.loads(path.read_text());canonical_package(value)
                    return value,download.suggested_filename

                unauth = playwright.request.new_context(base_url=origin)
                assert unauth.get(package_path+'?context_record_id='+quote(context_id,safe='')).status==401
                assert unauth.post(match_path+'/local-explanations',data={'context_record_id':context_id}).status==401
                unauth.dispose()
                initial = page.goto(origin+'/#token='+quote(token,safe=''),wait_until='domcontentloaded')
                assert initial and "script-src 'self'" in initial.headers['content-security-policy']
                assert "connect-src 'self'" in initial.headers['content-security-policy']
                expect(page.locator('#service-state')).to_contain_text('Server ready')
                retained = api('/matches/'+match_id+'/source-context')
                assert retained['availability']=='available' and retained['context_record_id']==context_id
                open_analysis()
                optional=page.locator('[data-context-ai]')
                expect(optional).to_contain_text('4 retained event rows')
                expect(optional).to_contain_text('Argentina: 1 squad entries')
                expect(optional).to_contain_text('France: 1 squad entries')
                expect(optional).to_contain_text('not official match statistics')
                expect(page.get_by_role('button',name='Use local model with source counts',exact=True)).to_be_enabled()
                assert jobs_count()==0 and not proof['submitted_jobs'] and not proof['provider_attempts']
                passed('Authenticated Analysis exposes three explicit synthetic source counts with CSP and no automatic job or provider request')

                package,filename=exported('export-context-package','synthetic-context-package.json')
                assert package==expected_package and filename.startswith('dragonhydra-sports-context-')
                assert package['schema_version']==local_ai.SCHEMA_CONTEXT and len(package['allowed_facts'])==len(fixture.package2_before_context['allowed_observations'])+3
                for absent in ('Argentina Player','"original"','"lineup"','"projection"','raw_reference'):
                    assert absent not in json.dumps(package)
                last=next(item for item in reversed(proof['requests']) if item['path']==package_path)
                assert parse_qs(last['query'])=={'context_record_id':[context_id]}
                assert jobs_count()==0
                passed('Explicit package/3 browser export freezes exact C1 and independently verifies canonical hash, bounds and absence of source arrays')

                mode['abort_next_context_post']=True;mode['expected_transport_error']=True
                page.locator('[data-action="local-explain-context"]').click()
                expect(page.locator('.job-progress')).to_contain_text('Job needs attention')
                first=proof['submitted_jobs'][-1]
                assert first['payload']=={'context_record_id':context_id} and first['idempotency_key']
                queued=job_wait(first['queued_job_id_before_browser_abort'])
                assert queued['status']=='succeeded' and queued['attempts']==1 and jobs_count()==1
                page.get_by_role('button',name='Dismiss',exact=True).click()
                replay=submit('local-explain-context')
                second=proof['submitted_jobs'][-1]
                assert second['payload']==first['payload'] and second['idempotency_key']==first['idempotency_key']
                assert replay['id']==queued['id'] and jobs_count()==1 and len(proof['fake_inference_calls'])==1
                mode['expected_transport_error']=False
                result=replay['result'];assert result['input_manifest']==expected_manifest and len(result['evidence'])==3
                assert result['runtime']['interface']=='SYNTHETIC/browser-fixture'
                expect(page.locator('#explanation-result')).to_contain_text('LOCAL MODEL · SOURCE FACT SELECTION')
                expect(page.locator('#explanation-result')).to_contain_text('contains 4 event rows')
                links=page.locator('#explanation-result .explanation-citation')
                expect(links).to_have_count(3)
                assert links.evaluate_all('(nodes)=>nodes.map(x=>x.getAttribute("href"))')==[urljoin(origin,x['url']) for x in result['evidence']]
                screenshot(page,'SYNTHETIC-context-selection.png')
                passed('Ambiguous queued POST is manually replayed with the same key/job; synthetic accepted selection displays exact three citations and full manifest',application_post_attempts=2,jobs=1)

                mode['configured']=False
                fallback=submit('local-explain-context')
                assert fallback['id']!=replay['id'] and fallback['result']['kind']=='deterministic'
                assert fallback['result']['input_manifest']==expected_manifest and len(fallback['result']['evidence'])==1
                assert fallback['result']['observations']==[expected_package['allowed_facts'][0]['observation']]
                assert len(proof['fake_inference_calls'])==1
                expect(page.locator('#explanation-result')).to_contain_text('AI_NOT_CONFIGURED')
                expect(page.locator('#explanation-result')).to_contain_text('DETERMINISTIC EVIDENCE SUMMARY')
                expect(page.locator('#explanation-result .explanation-citation')).to_have_count(1)
                assert proof['submitted_jobs'][-1]['idempotency_key']!=first['idempotency_key']
                screenshot(page,'SYNTHETIC-unconfigured-fallback.png')
                passed('A new explicit unconfigured context request keeps status-only deterministic fallback, E1 citation and all four input IDs')

                ordinary=submit('explain')
                assert ordinary['result']['kind']=='deterministic' and ordinary['result']['input_manifest']==[expected_manifest[0]]
                assert proof['submitted_jobs'][-1]['payload']=={}
                mode['configured']=True
                local=submit('local-explain')
                assert local['result']['kind']=='local_llm' and local['result']['input_manifest']==[expected_manifest[0]]
                assert len(local['result']['evidence'])==1 and proof['submitted_jobs'][-1]['payload']=={}
                assert proof['fake_inference_calls'][-1]['schema_version']==local_ai.SCHEMA
                package2,filename=exported('export-sports-package','synthetic-default-package.json')
                assert package2==fixture.package2_before_context and package2['schema_version']==local_ai.SCHEMA
                assert not filename.startswith('dragonhydra-sports-context-')
                last=next(item for item in reversed(proof['requests']) if item['path']==package_path)
                assert last['query']==''
                default_enabled()
                passed('All four existing controls remain enabled; ordinary Explain, local selection and exported package retain package/2 semantics')

                mode['terminal_next_inference']=True
                failed=submit('local-explain-context')
                assert failed['status']=='failed' and failed['attempts']==1
                terminal_key=proof['submitted_jobs'][-1]['idempotency_key']
                expect(page.locator('.job-progress')).to_contain_text('Job needs attention')
                page.get_by_role('button',name='Dismiss',exact=True).click()
                retried=submit('local-explain-context')
                assert retried['status']=='succeeded' and retried['id']!=failed['id']
                assert proof['submitted_jobs'][-1]['idempotency_key']!=terminal_key
                assert retried['result']['input_manifest']==expected_manifest
                passed('A known terminal synthetic failure clears its intent; the next explicit click uses a fresh key and job')

                before_negative=jobs_count();before_posts=len(proof['submitted_jobs'])
                for status in ('not_requested','parent_changed','available_wrong_parent','unavailable','404'):
                    mode['context_response']=status
                    page.reload(wait_until='domcontentloaded')
                    page.get_by_role('tab',name='Analysis',exact=True).click()
                    expect(page.locator('[data-action="explain"]')).to_be_enabled()
                    default_enabled()
                    expect(page.locator('[data-action="local-explain-context"]')).to_have_count(0)
                    expect(page.locator('[data-action="export-context-package"]')).to_have_count(0)
                    if status=='404':expect(page.locator('[data-context-ai]')).to_have_count(0)
                    else:expect(page.locator('[data-context-ai]')).to_be_visible()
                    proof['synthetic_ui_status_overrides'].append(status)
                assert jobs_count()==before_negative and len(proof['submitted_jobs'])==before_posts
                mode['context_response']='actual';page.reload(wait_until='domcontentloaded')
                page.get_by_role('tab',name='Analysis',exact=True).click()
                expect(page.locator('[data-action="local-explain-context"]')).to_be_enabled()
                for width in (1500,1024):
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'), 'Horizontal viewport overflow'
                screenshot(page,'SYNTHETIC-optional-controls-1024.png')
                passed('Not-requested, changed-parent, unavailable and older-API fixtures preserve defaults without automatic writes; controls fit 1500/1024 viewports')

                assert not proof['page_errors'] and not proof['unexpected_console_errors']
                assert not proof['provider_attempts'] and not proof['external_network_attempts']
                assert not proof['blocked_browser_requests'] and not proof['unexpected_mutations']
                after=snapshot(fixture.product.state)
                preserved=('public_result_observations','connector_observations','connector_acquisitions','cognitive_records','cognitive_receipts','connector_attempts')
                for name in preserved:
                    if name in baseline['tables']:assert after['tables'][name]==baseline['tables'][name],name
                assert after['raw_files']==baseline['raw_files'] and after['schema_sha256']==baseline['schema_sha256']
                proof['sports_raw_schema_preserved']=True
                passed('Sports/context/acquisition/raw/schema evidence remains exact; only explicit owned jobs/outbox/auth rows change, with no provider/model activity')
                context.close();context=None
        proof['passed']=True
        return 0
    except BaseException:
        proof['error']=safe(traceback.format_exc())
        if context is not None:
            try:context.pages[0].screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception:pass
        raise
    finally:
        if context is not None:
            try:context.close()
            except Exception:pass
        if server is not None:server.should_exit=True
        if thread is not None and thread.ident is not None:thread.join(timeout=20)
        if listener is not None:listener.close()
        proof['owned_api_stopped']=thread is None or not thread.is_alive()
        proof['source_hashes_after']={path.relative_to(ROOT).as_posix():digest(path) for path in sources}
        proof['source_files_changed']=proof['source_hashes_after']!=proof['source_hashes_before']
        proof['passed']=proof['passed'] and proof['owned_api_stopped'] and not proof['source_files_changed']
        proof['finished_at']=datetime.now(timezone.utc).isoformat()
        (output/'journey.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        fixture.doCleanups()


if __name__=='__main__':raise SystemExit(main())
