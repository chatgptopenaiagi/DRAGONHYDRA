"""Actual installed primary Joomla Control Center acceptance, prepared for root execution.

Default: read-only browser/API/SQLite acceptance. --apply-workflow permits only
the two explicit selected-match Joomla commands and an idempotent forecast replay.
No provider request, import, local AI request, service control or native desktop
input belongs here. Credentials are owner-bound DPAPI inputs, held only in memory.
No traces, HAR, raw HTML, cookies, passwords or exception messages are saved.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/system-control-center-20261101/evidence'
STATE = ROOT / 'build/workstation/test-install/state data'
INSTALL = ROOT / 'build/workstation/test-install/application files'
ORIGIN = 'http://127.0.0.1:18740'
ADMIN = ORIGIN + '/administrator/'
COMPONENT = ADMIN + 'index.php?option=com_dragonhydra'
MATCH_ID = '11b9878fcff481ce5952b61d6df9dda8fd43ac21b29ae675aec8f2a1d3d40b1b'
GROUPS = {'infra': 'Infrastructure', 'data': 'Data', 'odds_prediction': 'Odds and prediction',
          'optional_ai': 'Optional AI', 'memory_evaluation': 'Memory and evaluation'}
STATES = {'ready': 'Ready', 'degraded': 'Degraded', 'unavailable': 'Unavailable',
          'configured_unverified': 'Configured, unverified', 'installed_not_configured': 'Installed, not configured',
          'not_implemented': 'Not implemented', 'not_applicable': 'Not applicable'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_record_ids(history):
    return {kind: sorted(row['record_id'] for row in history['records'].get(kind, []))
            for kind in ('models', 'predictions', 'outcomes', 'evaluations')}


def job_snapshot(database):
    """Fixed primary application store, read-only; never read job payloads or owners."""
    assert database.resolve() == (STATE / 'kernel/core.sqlite3').resolve() and database.is_file()
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute('SELECT id,kind,status FROM product_jobs ORDER BY id').fetchall()
    return {'ids': [row[0] for row in rows], 'count': len(rows),
            'ids_sha256': digest([row[0] for row in rows]),
            'states_sha256': digest(rows)}


def snapshot_evidence(before, after):
    return {'before_count': before['count'], 'after_count': after['count'],
            'before_ids_sha256': before['ids_sha256'], 'after_ids_sha256': after['ids_sha256'],
            'existing_job_statuses_changed': before['states_sha256'] != after['states_sha256']}


class Acceptance:
    def __init__(self, output, apply_workflow=False):
        self.output = output.resolve()
        assert self.output.parent == BASE.resolve() and re.fullmatch(r'browser-[A-Za-z0-9-]+', self.output.name)
        assert not self.output.exists(), 'Preserve earlier evidence'
        self.output.mkdir(parents=True)
        self.apply_workflow = apply_workflow
        self.private_values = []
        self.report = {'schema_version': 1, 'passed': False, 'started_at': utc(),
            'scope': 'Actual primary Joomla administrator in isolated headless Microsoft Edge contexts',
            'origin': ORIGIN, 'backend': 'http://127.0.0.1:18744/dragon/api/v1',
            'helper_sha256': digest(Path(__file__).read_bytes()), 'apply_workflow': apply_workflow,
            'stage': 'initialization', 'checks': [], 'screenshots': [], 'jobs': [],
            'page_errors': [], 'forbidden_requests': [], 'credentials_emitted': False,
            'raw_html_trace_har_cookies_saved': False, 'backend_credential_inserted_in_browser': False,
            'provider_requests_or_imports': False, 'local_ai_requests': False,
            'native_desktop_input': False, 'service_controls': False}

    def save(self):
        encoded = json.dumps(self.report, indent=2, ensure_ascii=False) + '\n'
        assert not any(value and value in encoded for value in self.private_values)
        temporary = self.output / 'verification.tmp.json'
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(self.output / 'verification.json')

    def check(self, name, passed=True, status=None, **evidence):
        state = status or ('PASS' if passed else 'FAIL')
        self.report['checks'].append({'name': name, 'status': state, 'verified_at': utc(), **evidence})
        self.save()
        if state == 'FAIL':
            raise AssertionError('Acceptance gate failed')

    def stage(self, value):
        self.report['stage'] = value
        self.save()

    def prepare(self):
        self.stage('exact_primary_binding')
        credentials = load('system_control_private_credentials', ROOT / 'tests/installation/joomla_frontend_credentials.py')
        self.credentials = credentials.load_credentials()
        self.api = credentials.load_recovery().Recovery()
        cfg = self.api.cfg
        assert Path(cfg['state_root']).resolve() == STATE.resolve()
        assert Path(cfg['install_root']).resolve() == INSTALL.resolve()
        assert cfg['service_name'] == 'DragonhydraWorkstationTest'
        assert (cfg['web_port'], cfg['database_port'], cfg['api_port']) == (18740, 18741, 18744)
        assert self.api.origin == ORIGIN and self.api.api == self.report['backend']
        assert cfg['api_base'] == self.api.api
        endpoint = json.loads((STATE / 'client/endpoint.json').read_text(encoding='utf-8-sig'))
        assert endpoint['url'] == 'http://127.0.0.1:18744'
        assert Path(cfg['bridge_secret_path']).resolve() == (STATE / 'kernel/joomla-bridge.json').resolve()
        pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
        probe = subprocess.run([pwsh, '-NoProfile', '-Command',
            'Get-CimInstance Win32_Service -Filter "Name=\'DragonhydraWorkstationTest\'" | Select-Object Name,State,ProcessId | ConvertTo-Json -Compress'],
            capture_output=True, text=True, timeout=20)
        assert probe.returncode == 0
        service = json.loads(probe.stdout)
        assert service['Name'] == cfg['service_name'] and service['State'] == 'Running' and service['ProcessId'] > 0
        self.private_values = [self.credentials['password'], self.api.token]
        self.private_values += [cfg.get(key, '') for key in ('root_password','db_password','core_db_password','admin_password')]
        values = [value for value in self.private_values if isinstance(value, str) and value]
        self.private_values = list(set(values + [quote(value, safe='') for value in values] + [html.escape(value, quote=True) for value in values]))
        self.database = STATE / 'kernel/core.sqlite3'
        self.check('exact_primary_profile_and_running_service', service=service, ports={'joomla':18740,'api':18744,'mariadb':18741},
                   bridge_secret_file_read=False)
        self.baseline = self.api.snapshot()
        self.registry = self.api.api_read('/system/modules')
        self.system = self.api.api_read('/system')
        assert self.registry['schema_version'] == 1 and self.registry['read_only'] is True
        assert self.registry['network_probes'] is False and len(self.registry['modules']) == 18
        self.match = self.api.api_read('/matches/' + MATCH_ID)
        assert self.match['id'] == MATCH_ID
        if self.apply_workflow:
            assert self.match['status'] == 'scheduled'
        self.history_before = self.api.api_read('/matches/' + MATCH_ID + '/cognition-history')
        self.check('associated_backend_registry_and_real_retained_match', total_modules=18,
                   match={key:self.match[key] for key in ('id','source_id','event_date','status')},
                   baseline_records=self.baseline['records'], workflow_counts=self.history_before['counts'])

    def watch(self, context):
        def guard(route):
            request = route.request
            parts = urlsplit(request.url)
            same = parts.scheme + '://' + parts.netloc == ORIGIN
            query = parse_qs(parts.query)
            allowed = same and request.method in ('GET','HEAD') and not parts.path.startswith('/dragon/')
            if same and request.method == 'POST' and parts.path == '/administrator/index.php':
                body = parse_qs(request.post_data or '')
                task = query.get('task', body.get('task', ['']))[0]
                option = query.get('option', body.get('option', ['']))[0]
                allowed = option == 'com_login' and task == 'login'
                if self.apply_workflow and option == 'com_dragonhydra' and task in ('actions.forecast','actions.evaluate'):
                    allowed = body.get('match_id') == [MATCH_ID]
            if not allowed:
                self.report['forbidden_requests'].append({'method':request.method,'reason':'Outside fixed Joomla browser allowlist'})
                route.abort()
            else:
                route.continue_()
        context.route('**/*', guard)
        context.on('page', lambda page: page.on('pageerror', lambda error: self.report['page_errors'].append({'class':type(error).__name__})))

    def no_secrets(self, page):
        content = page.content()
        storage = page.evaluate('({local:{...localStorage},session:{...sessionStorage}})')
        serialized = content + json.dumps(storage)
        assert not any(value and value in serialized for value in self.private_values)
        assert not page.locator('input[type=password]:visible').count()
        return {'private_value_matches':0,'local_storage_entries':len(storage['local']),'session_storage_entries':len(storage['session'])}

    def route(self, page, **values):
        query = {'section':'control'} | values
        page.goto(COMPONENT + '&' + urlencode(query), wait_until='domcontentloaded')
        expect = self.expect
        expect(page.get_by_role('heading', name='System Control Center', exact=True)).to_be_visible()
        expect(page.locator('#mod-login-username')).to_have_count(0)
        self.no_secrets(page)

    def login(self, page, name):
        page.goto(ADMIN, wait_until='domcontentloaded')
        username = page.locator('#mod-login-username')
        self.expect(username).to_be_visible()
        form = username.locator('xpath=ancestor::form[1]')
        action = urljoin(ADMIN, form.get_attribute('action') or '')
        assert urlsplit(action).scheme + '://' + urlsplit(action).netloc == ORIGIN
        assert urlsplit(action).path == '/administrator/index.php'
        names = form.locator('input[type=hidden]').evaluate_all('(nodes)=>nodes.map(n=>n.name)')
        assert sum(bool(re.fullmatch('[a-f0-9]{32}', item)) for item in names) == 1
        username.fill(self.credentials['username'])
        form.locator('input[type=password]').fill(self.credentials['password'])
        form.locator('button[type=submit],input[type=submit]').first.click()
        page.wait_for_load_state('domcontentloaded')
        self.route(page)
        self.expect(page.locator('.header-profile')).to_be_visible()
        self.check(name, genuine_login_form_csrf=True, imported_storage_state=False,
                   positive_indicators=['authenticated administrator profile','protected Control Center','registry data'],
                   **self.no_secrets(page))

    def screenshot(self, page, name):
        self.no_secrets(page)
        path = self.output / name
        page.locator('.dh-control').screenshot(path=str(path), animations='disabled')
        self.report['screenshots'].append({'path':str(path),'sha256':digest(path.read_bytes()),
            'scope':'Authenticated component only; no login, Options or secret-entry fields'})
        self.save()

    def compare_registry(self, page):
        self.route(page)
        rows = page.locator('[aria-label="Scrollable module status table"] tbody tr')
        self.expect(rows).to_have_count(18)
        actual = self.api.api_read('/system/modules')
        rendered_states = {}
        for item in actual['modules']:
            definition, observation = item['definition'], item['observation']
            row = rows.filter(has=page.locator('th .dc-code', has_text=re.compile('^'+re.escape(definition['module_id'])+'$')))
            self.expect(row).to_have_count(1)
            self.expect(row.locator('th a')).to_have_text(definition['display_name'])
            self.expect(row.locator('.dc-badge')).to_have_text(STATES[observation['runtime_state']])
            self.expect(row).to_contain_text(observation['reason'])
            rendered_states[definition['module_id']] = observation['runtime_state']
        self.expect(page.locator('[data-module-total]')).to_have_attribute('data-module-total', '18')
        system = self.api.api_read('/system')
        for key in ('source_sha','source_content_sha256'):
            expected = system.get('build', {}).get(key) or 'Not reported'
            self.expect(page.locator('[data-backend-build="'+key+'"]').first).to_have_text(expected)
        self.check('all_eighteen_module_statuses_and_running_build_match_api', module_states=rendered_states,
                   build={key:system.get('build',{}).get(key) for key in ('version','build_kind','source_sha','source_content_sha256')})

    def menu_navigation(self, page):
        self.stage('real_joomla_control_center_menu')
        navigation = page.locator('.main-nav-container')
        control = navigation.locator('a[href*="option=com_dragonhydra"][href*="section=control"]').first
        if not control.is_visible():
            dragon = navigation.locator('a[aria-label="DRAGONHYDRA"]').first
            if not dragon.is_visible():
                navigation.get_by_role('link',name='Components',exact=True).click()
            if not control.is_visible():
                dragon.click()
        self.expect(control).to_be_visible(); control.click(); page.wait_for_load_state('domcontentloaded')
        self.expect(page.get_by_role('heading',name='System Control Center',exact=True)).to_be_visible()
        self.check('control_center_opens_from_existing_joomla_administrator_menu',menu_path=['Components','DRAGONHYDRA','System Control Center'])

    def groups_details_and_metrics(self, page):
        for key, label in GROUPS.items():
            self.stage('module_group_'+key)
            expected = [item['definition']['module_id'] for item in self.registry['modules'] if item['definition']['category'] == key]
            page.locator('.dc-groups').get_by_role('link',name=re.compile('^'+re.escape(label))).click()
            page.wait_for_load_state('domcontentloaded')
            rows = page.locator('[aria-label="Scrollable module status table"] tbody tr')
            self.expect(rows).to_have_count(len(expected))
            shown = rows.locator('th .dc-code').all_inner_texts()
            assert sorted(shown) == sorted(expected)
        self.check('all_five_group_navigation_filters_existing_modules', groups=list(GROUPS))
        self.stage('module_status_filter')
        self.route(page)
        page.get_by_label('Runtime status', exact=True).select_option('configured_unverified')
        page.get_by_role('button', name='Apply filters', exact=True).click(); page.wait_for_load_state('domcontentloaded')
        assert page.locator('[aria-label="Scrollable module status table"] .dc-badge').count()>0
        for badge in page.locator('[aria-label="Scrollable module status table"] .dc-badge').all():
            self.expect(badge).to_have_text('Configured, unverified')
        self.check('actual_status_filter_form', selected_status='configured_unverified')
        self.stage('module_detail_metrics')
        self.route(page, module_id='data_engine')
        details = page.locator('#dc-detail')
        actual = next(item for item in self.api.api_read('/system/modules')['modules'] if item['definition']['module_id']=='data_engine')
        self.expect(details.get_by_role('heading', name=actual['definition']['display_name'], exact=True)).to_be_visible()
        metrics = actual['observation']['sanitized_metrics']
        heading = details.get_by_role('heading',name='Sanitized retained metrics',exact=True)
        displayed = heading.locator('xpath=parent::section').locator('dl').evaluate('(dl)=>Object.fromEntries([...dl.querySelectorAll("dt")].map(dt=>[dt.textContent.trim(),dt.nextElementSibling.textContent.trim()]))')
        expected = {key.replace('_',' ').capitalize(): 'Yes' if value is True else 'No' if value is False else str(value) for key,value in metrics.items()}
        assert displayed == expected
        self.expect(details.get_by_role('heading',name='Dependencies',exact=True)).to_be_visible()
        self.expect(details.get_by_role('heading',name='Configuration requirements',exact=True)).to_be_visible()
        self.check('module_detail_dependencies_evidence_and_metrics_match_backend', module_id='data_engine', metrics=metrics,
                   configuration_values_displayed=False)
        self.stage('supervisor_service_identity')
        self.route(page,module_id='supervisor')
        actual = next(item for item in self.api.api_read('/system/modules')['modules'] if item['definition']['module_id']=='supervisor')
        service_name=actual['observation']['sanitized_metrics'].get('service_name')
        assert service_name==self.api.cfg['service_name']=='DragonhydraWorkstationTest'
        details=page.locator('#dc-detail')
        self.expect(details.get_by_role('heading',name=actual['definition']['display_name'],exact=True)).to_be_visible()
        self.expect(details).to_contain_text('Service name')
        self.expect(details).to_contain_text(service_name)
        self.check('supervisor_detail_shows_actual_pid_bound_windows_service',module_id='supervisor',service_name=service_name)

    def no_jobs_from_reads(self, page, name):
        before = job_snapshot(self.database)
        history = public_record_ids(self.api.api_read('/matches/'+MATCH_ID+'/cognition-history'))
        self.route(page, match_id=MATCH_ID)
        page.get_by_role('link', name='Refresh status', exact=True).click(); page.wait_for_load_state('domcontentloaded')
        page.reload(wait_until='domcontentloaded')
        after_history = public_record_ids(self.api.api_read('/matches/'+MATCH_ID+'/cognition-history'))
        after = job_snapshot(self.database)
        self.check(name, before['ids']==after['ids'] and history==after_history,
                   jobs=snapshot_evidence(before,after), record_ids_sha256=digest(after_history),
                   sqlite_mode='ro/query_only', hmac_nonce_security_bookkeeping_excluded=True)

    def submit(self, page, button):
        page.get_by_role('button',name=button,exact=True).click(); page.wait_for_load_state('domcontentloaded')
        query = parse_qs(urlsplit(page.url).query)
        assert query.get('section') == ['jobs']
        job_id = query.get('job_id',[''])[0]
        assert re.fullmatch('[a-f0-9]{32}',job_id)
        self.expect(page.get_by_role('heading',name='Retained workflow job',exact=True)).to_be_visible()
        deadline = time.monotonic()+90
        while True:
            job = self.api.api_read('/jobs/'+job_id)
            if job['status'] in ('succeeded','failed','cancelled'):
                break
            assert time.monotonic()<deadline
            page.get_by_role('link',name='Refresh job status',exact=True).click()
            page.wait_for_load_state('domcontentloaded'); time.sleep(.3)
        page.get_by_role('link',name='Refresh job status',exact=True).click(); page.wait_for_load_state('domcontentloaded')
        assert job['status']=='succeeded'
        return job

    def workflow(self, page):
        if not self.apply_workflow:
            self.check('explicit_forecast_and_evaluation_jobs', status='NOT_RUN', reason='Use --apply-workflow to authorize these two selected-match commands.')
            return
        self.stage('explicit_forecast_command')
        self.route(page,match_id=MATCH_ID)
        forecast = self.submit(page,'Create and retain forecast')
        result = forecast['result']
        models, predictions = result['model_runs'],result['predictions']
        assert result['status']=='persisted' and len(models)==5 and len(predictions)==5
        model_ids = sorted(row['record_id'] for row in models)
        prediction_ids = sorted(row['record_id'] for row in predictions)
        page.get_by_role('link',name='Read persisted workflow history',exact=True).click(); page.wait_for_load_state('domcontentloaded')
        history = self.api.api_read('/matches/'+MATCH_ID+'/cognition-history')
        ids = public_record_ids(history)
        assert set(model_ids)<=set(ids['models']) and set(prediction_ids)<=set(ids['predictions'])
        panel = page.locator('#dc-workflow')
        for record_id in model_ids+prediction_ids:
            self.expect(panel).to_contain_text(record_id)
        self.expect(panel).to_contain_text(history['target_evidence_id'])
        for prediction in predictions:
            row = panel.locator('table').first.locator('tbody tr').filter(has_text=prediction['record_id'])
            cells = row.locator('td').all_inner_texts()
            assert prediction['model_run_id'] in row.inner_text()
            for position,outcome in enumerate(('home','draw','away')):
                assert cells[position].endswith('%')
                assert abs(Decimal(cells[position].rstrip('%'))-Decimal(str(prediction['probabilities'][outcome]))*100)<=Decimal('.005')
        first_model = models[0]
        model_item = panel.locator('ul.dc-list > li').filter(has_text=first_model['record_id']).first
        model_item.locator('summary').click()
        for value in (first_model['model_name'],first_model['model_version'],first_model['data_cutoff'],first_model['parameters']['workflow']['generated_at']):
            self.expect(model_item).to_contain_text(value)
        for item in first_model['parameters']['workflow']['uncertainty']['items']:
            self.expect(model_item).to_contain_text(item)
        self.check('explicit_ui_forecast_persists_five_models_and_predictions_visible_in_joomla', job_id=forecast['id'],
                   result_status=result['status'], model_record_ids=model_ids,prediction_record_ids=prediction_ids,
                   match_id=MATCH_ID,target_evidence_id=history['target_evidence_id'],history_counts=history['counts'])
        self.report['jobs'].append({'id':forecast['id'],'kind':forecast['kind'],'status':forecast['status'],'result_status':result['status']})
        self.screenshot(page,'retained-workflow-desktop.png')
        before = job_snapshot(self.database)
        self.route(page,match_id=MATCH_ID)
        replay = self.submit(page,'Create and retain forecast')
        after = job_snapshot(self.database)
        self.check('repeated_explicit_forecast_reuses_session_command_and_job', replay['id']==forecast['id'] and before['ids']==after['ids'],
                   job_id=replay['id'], jobs=snapshot_evidence(before,after))
        self.stage('explicit_evaluation_command')
        self.route(page,match_id=MATCH_ID)
        evaluation = self.submit(page,'Evaluate retained forecast')
        result = evaluation['result']
        assert result['status']=='pending' and result['reason']=='LATER_RETAINED_OUTCOME_UNAVAILABLE'
        assert not result['persisted_evaluations']
        self.expect(page.locator('.dragonhydra-administration')).to_contain_text('Pending is not a successful evaluation')
        self.expect(page.locator('.dragonhydra-administration')).to_contain_text(result['reason'])
        page.get_by_role('link',name='Read persisted workflow history',exact=True).click(); page.wait_for_load_state('domcontentloaded')
        self.expect(page.locator('#dc-workflow')).to_contain_text('No eligible later outcome is attached')
        self.check('explicit_ui_evaluation_reports_pending_without_false_performance', job_id=evaluation['id'],
                   job_status=evaluation['status'],result_status=result['status'],reason=result['reason'],persisted_evaluations=0)
        self.report['jobs'].append({'id':evaluation['id'],'kind':evaluation['kind'],'status':evaluation['status'],'result_status':result['status'],'reason':result['reason']})
        self.no_jobs_from_reads(page,'post_terminal_refresh_reload_and_history_create_no_new_jobs_or_records')

    def run(self):
        # Import only during explicit execution, so helpers and syntax checks do not launch a browser.
        from playwright.sync_api import sync_playwright, expect
        self.expect = expect
        browser = context = None
        try:
            self.prepare()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge',headless=True)
                context = browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
                self.watch(context); page = context.new_page()
                self.stage('anonymous_protection')
                page.goto(COMPONENT+'&section=control',wait_until='domcontentloaded')
                expect(page.locator('#mod-login-username')).to_be_visible()
                expect(page.locator('.dh-control')).to_have_count(0)
                self.check('anonymous_control_center_requires_genuine_admin_login')
                self.stage('genuine_administrator_login')
                self.login(page,'genuine_owner_administrator_login_and_protected_navigation')
                self.stage('control_registry_comparison')
                self.compare_registry(page)
                self.menu_navigation(page)
                self.screenshot(page,'system-control-desktop.png')
                self.groups_details_and_metrics(page)
                self.screenshot(page,'module-detail-desktop.png')
                self.no_jobs_from_reads(page,'get_refresh_reload_and_history_create_no_new_jobs_or_records')
                self.stage('csrf_protection')
                denied = context.request.post(COMPONENT+'&task=actions.forecast',form={'match_id':MATCH_ID})
                self.check('authenticated_workflow_post_without_csrf_is_denied', denied.status==403,http_status=denied.status)
                self.workflow(page)
                self.stage('responsive_secret_safe_layout')
                self.route(page,match_id=MATCH_ID)
                self.check('desktop_layout_has_no_document_overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
                page.set_viewport_size({'width':390,'height':844}); page.reload(wait_until='domcontentloaded')
                self.check('narrow_390px_layout_has_no_document_overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
                self.screenshot(page,'system-control-mobile.png')
                scripts=0
                for url in page.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)'):
                    if urlsplit(url).scheme+'://'+urlsplit(url).netloc==ORIGIN:
                        source=context.request.get(url).text()
                        assert not any(value and value in source for value in self.private_values)
                        scripts+=1
                self.check('rendered_html_local_scripts_and_browser_storage_omit_private_values',local_scripts_checked=scripts,**self.no_secrets(page))
                self.stage('real_joomla_logout')
                final_history=public_record_ids(self.api.api_read('/matches/'+MATCH_ID+'/cognition-history'))
                page.locator('.header-profile > button.dropdown-toggle:visible').first.click()
                logout=page.locator('.header-profile a[href*="option=com_login"][href*="task=logout"]:visible').first
                expect(logout).to_be_visible(); logout.click(); page.wait_for_load_state('domcontentloaded')
                page.goto(COMPONENT+'&section=control',wait_until='domcontentloaded')
                expect(page.locator('#mod-login-username')).to_be_visible(); expect(page.locator('.dh-control')).to_have_count(0)
                self.check('real_logout_revokes_protected_component_access')
                context.close(); context=None; browser.close(); browser=None
                self.stage('fresh_browser_login')
                browser=playwright.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
                self.watch(context); page=context.new_page()
                self.login(page,'fresh_edge_context_owner_login_reopens_control_center')
                self.route(page,match_id=MATCH_ID)
                reopened_history=public_record_ids(self.api.api_read('/matches/'+MATCH_ID+'/cognition-history'))
                for record_id in reopened_history['models']+reopened_history['predictions']:
                    self.expect(page.locator('#dc-workflow')).to_contain_text(record_id)
                self.check('fresh_login_retains_backend_workflow_history',reopened_history==final_history,
                           storage_state_imported=False,**self.no_secrets(page))
                context.close(); context=None; browser.close(); browser=None
            current=self.api.snapshot()
            self.check('retained_matches_provider_settings_pairing_and_workstation_config_preserved',current==self.baseline,
                       records=current['records'],matches_sha256=current['all_matches_sha256'],configuration_hashes=current['configuration_sha256'])
            self.check('no_blocking_page_errors_or_unapproved_browser_requests',not self.report['page_errors'] and not self.report['forbidden_requests'],
                       page_errors=len(self.report['page_errors']),forbidden_requests=len(self.report['forbidden_requests']))
            self.report['passed']=True; self.report['stage']='complete'
        except Exception as error:
            self.report['failure']={'class':type(error).__name__}
            if not self.report['checks'] or self.report['checks'][-1]['status']!='FAIL':
                self.report['checks'].append({'name':'stage_'+self.report['stage'],'status':'FAIL',
                                              'verified_at':utc(),'failure_class':type(error).__name__})
        finally:
            if context is not None:
                try: context.close()
                except Exception: pass
            if browser is not None:
                try: browser.close()
                except Exception: pass
            self.report['finished_at']=utc(); self.report['browser_closed']=True; self.save()
        return 0 if self.report['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=BASE/'browser-r1')
    parser.add_argument('--apply-workflow',action='store_true',help='Explicitly submit selected-match forecast/evaluation through genuine Joomla forms.')
    args=parser.parse_args()
    try:
        acceptance=Acceptance(args.output,args.apply_workflow)
        code=acceptance.run()
        print(json.dumps({'passed':acceptance.report['passed'],'checks':len(acceptance.report['checks']),
                          'stage':acceptance.report['stage'],'report':str(acceptance.output/'verification.json')}))
        return code
    except Exception as error:
        print(json.dumps({'passed':False,'failure':{'class':type(error).__name__},'credentials_emitted':False}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
